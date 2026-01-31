#!/usr/bin/env python3
"""Blue/Green Deployment Manager CLI."""
import sys
import time
import subprocess
from pathlib import Path
from typing import Dict, Optional
import click


def get_iac_root() -> Path:
    """Get the root directory of the IAC repo.

    This allows the deploy manager to work from any directory.
    """
    # This file is at deploy_manager/deploy_manager/cli.py
    # IAC root is ../../ from here
    return Path(__file__).resolve().parent.parent.parent
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
from rich import box

from .aws_client import AWSClient
from .config import Config
from .ecr_client import ECRClient
from .deploy_state import DeployState


console = Console()


class DeploymentManager:
    """Manages blue/green deployments."""

    def __init__(self, config: Config):
        self.config = config
        self.aws = AWSClient(region=config.region)

    def get_active_environment(self) -> str:
        """Determine which environment is currently active."""
        # Check which target group the listener is pointing to
        try:
            result = subprocess.run(
                ["terraform", "-chdir=terraform/prod", "output", "-json", "active_color"],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,  # Add timeout to prevent hanging on state lock
                cwd=get_iac_root()
            )
            import json
            active = json.loads(result.stdout)
            return active.strip('"')
        except subprocess.TimeoutExpired:
            # Timeout likely means state is locked by another terraform process
            console.print("[yellow]Warning: Terraform state is locked. Falling back to instance detection.[/yellow]", style="dim")
            # Fall through to fallback logic
        except Exception:
            # Fallback: check which environment has instances
            blue_info = self.aws.get_asg_info(self.config.blue_asg)
            green_info = self.aws.get_asg_info(self.config.green_asg)

            blue_capacity = blue_info["DesiredCapacity"] if blue_info else 0
            green_capacity = green_info["DesiredCapacity"] if green_info else 0

            if blue_capacity > 0 and green_capacity == 0:
                return "blue"
            elif green_capacity > 0 and blue_capacity == 0:
                return "green"
            else:
                return "unknown"

    def get_active_capacity(self) -> int:
        """Get the desired capacity of the currently active environment."""
        active_env = self.get_active_environment()
        asg_name = self.config.blue_asg if active_env == "blue" else self.config.green_asg

        asg_info = self.aws.get_asg_info(asg_name)
        if asg_info:
            return asg_info["DesiredCapacity"]
        return 1  # Default fallback

    def show_status(self):
        """Display comprehensive deployment status."""
        active_env = self.get_active_environment()

        # Get status for both environments
        blue_status = self.aws.get_environment_status(
            self.config.blue_asg,
            self.config.blue_target_groups
        )
        green_status = self.aws.get_environment_status(
            self.config.green_asg,
            self.config.green_target_groups
        )

        # Create header
        header = Text()
        header.append("Superschedules Blue/Green Deployment Status\n", style="bold cyan")
        header.append(f"Active Environment: ", style="bold")
        if active_env == "blue":
            header.append("BLUE", style="bold blue")
        elif active_env == "green":
            header.append("GREEN", style="bold green")
        else:
            header.append("UNKNOWN", style="bold yellow")

        console.print(Panel(header, box=box.DOUBLE))
        console.print()

        # Display both environments side by side
        self._display_environment("Blue", blue_status, active_env == "blue")
        console.print()
        self._display_environment("Green", green_status, active_env == "green")
        console.print()

        # Display total costs
        total_cost = blue_status.get("total_hourly_cost", 0) + green_status.get("total_hourly_cost", 0)
        cost_table = Table(title="Cost Summary", box=box.ROUNDED)
        cost_table.add_column("Metric", style="cyan")
        cost_table.add_column("Value", style="green")
        cost_table.add_row("Hourly Cost", f"${total_cost:.4f}/hr")
        cost_table.add_row("Daily Cost", f"${total_cost * 24:.2f}/day")
        cost_table.add_row("Monthly Cost (est)", f"${total_cost * 730:.2f}/mo")
        console.print(cost_table)

    def _display_environment(self, name: str, status: Dict, is_active: bool):
        """Display single environment status."""
        color = "blue" if name == "Blue" else "green"
        title_style = f"bold {color}"

        if is_active:
            title = f"{name} Environment (ACTIVE)"
        else:
            title = f"{name} Environment"

        if not status["exists"] or status["desired_capacity"] == 0:
            console.print(Panel(
                f"[yellow]No instances running[/yellow]",
                title=title,
                title_align="left",
                border_style=color,
                box=box.ROUNDED
            ))
            return

        # Create instances table
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        table.add_column("Instance ID", style="cyan")
        table.add_column("Type", style="white")
        table.add_column("Lifecycle", style="yellow")
        table.add_column("State", style="white")
        table.add_column("Uptime", style="white")
        table.add_column("Cost", style="green")

        for instance in status["instances"]:
            uptime = instance["uptime"]
            uptime_str = f"{uptime['days']}d {uptime['hours']}h {uptime['minutes']}m"

            lifecycle_display = "Spot" if instance["lifecycle"] == "spot" else "On-Demand"
            lifecycle_style = "yellow" if instance["lifecycle"] == "spot" else "blue"

            state = instance["state"]
            state_style = "green" if state == "running" else "red"

            table.add_row(
                instance["instance_id"],
                instance["instance_type"],
                f"[{lifecycle_style}]{lifecycle_display}[/{lifecycle_style}]",
                f"[{state_style}]{state}[/{state_style}]",
                uptime_str,
                f"${instance['hourly_cost']:.4f}/hr"
            )

        # Health status - show both health state and traffic routing
        health_text = Text()
        health_parts = []

        for tg_name, tg_health in status["health"].items():
            if not tg_health:
                health_parts.append((tg_name, "no targets", "yellow", None))
                continue

            # Count different states
            healthy_count = sum(1 for t in tg_health if t["TargetHealth"]["State"] == "healthy")
            unused_count = sum(1 for t in tg_health if t["TargetHealth"]["State"] == "unused")
            unhealthy_count = sum(1 for t in tg_health if t["TargetHealth"]["State"] == "unhealthy")
            initial_count = sum(1 for t in tg_health if t["TargetHealth"]["State"] == "initial")
            total_count = len(tg_health)

            # Determine status and styling
            if healthy_count == total_count:
                # All healthy and receiving traffic (active environment)
                health_parts.append((tg_name, f"{healthy_count}/{total_count} ✓ receiving traffic", "green", "●"))
            elif unused_count == total_count:
                # All unused - ready but not receiving traffic (inactive environment)
                health_parts.append((tg_name, f"{unused_count}/{total_count} ✓ ready (not receiving traffic)", "cyan", "○"))
            elif initial_count > 0:
                # Still initializing
                health_parts.append((tg_name, f"{initial_count}/{total_count} initializing...", "yellow", "◐"))
            elif unhealthy_count > 0:
                # Some unhealthy
                health_parts.append((tg_name, f"{unhealthy_count}/{total_count} failing checks", "red", "✗"))
            else:
                # Mixed state
                health_parts.append((tg_name, f"mixed state", "yellow", "◐"))

        # Format health status in a compact, readable way
        health_text.append("\n", style="white")
        for i, (tg_name, status_text, style, icon) in enumerate(health_parts):
            if i > 0:
                health_text.append("\n", style="white")
            if icon:
                health_text.append(f"{icon} ", style=style)
            health_text.append(f"{tg_name}: ", style="bold white")
            health_text.append(status_text, style=style)

        # Capacity info
        capacity_text = Text()
        capacity_text.append(f"Capacity: {status['desired_capacity']}", style="white")
        capacity_text.append(f" (min: {status['min_size']}, max: {status['max_size']})", style="dim")

        # Cost info
        cost_text = Text()
        cost_text.append(f"\n💰 Cost: ", style="white")
        cost_text.append(f"${status['total_hourly_cost']:.4f}/hr", style="green")
        cost_text.append(f" (${status['total_monthly_cost']:.2f}/mo est)", style="dim green")

        # Combine all info - use Group to combine renderables
        from rich.console import Group

        content_items = [
            capacity_text,
            health_text,
            cost_text,
            Text("\n"),
            table
        ]

        console.print(Panel(
            Group(*content_items),
            title=title,
            title_align="left",
            border_style=color,
            box=box.ROUNDED
        ))

    def deploy_to_inactive(self, skip_confirm: bool = False):
        """Deploy to the inactive environment and monitor progress."""
        active_env = self.get_active_environment()

        if active_env == "unknown":
            console.print("[red]Cannot determine active environment. Please check manually.[/red]")
            return False

        target_env = "green" if active_env == "blue" else "blue"

        console.print(f"\n[bold]Current active environment:[/bold] [cyan]{active_env.upper()}[/cyan]")
        console.print(f"[bold]Deploying to:[/bold] [cyan]{target_env.upper()}[/cyan]\n")

        # Confirm deployment (unless skipped)
        if not skip_confirm and not click.confirm(f"Deploy new version to {target_env.upper()}?", default=True):
            console.print("[yellow]Deployment cancelled.[/yellow]")
            return False

        # Start deployment
        console.print(f"\n[bold cyan]Starting deployment to {target_env}...[/bold cyan]\n")

        try:
            # Get active environment's current capacity to preserve it
            active_asg = self.config.blue_asg if active_env == "blue" else self.config.green_asg
            active_asg_info = self.aws.get_asg_info(active_asg)

            if active_asg_info:
                active_capacity = active_asg_info["DesiredCapacity"]
                active_min = active_asg_info["MinSize"]
                active_max = active_asg_info["MaxSize"]
            else:
                # Fallback to defaults if we can't get ASG info
                active_capacity = 1
                active_min = 1
                active_max = 2

            # Run make deploy command with active environment capacity preserved
            cmd = (f"make deploy:new-{target_env} "
                   f"ACTIVE_DESIRED_CAPACITY={active_capacity} "
                   f"ACTIVE_MIN_SIZE={active_min} "
                   f"ACTIVE_MAX_SIZE={active_max}")
            console.print(f"[dim]Running: {cmd}[/dim]\n")
            console.print(f"[dim]Preserving {active_env} capacity: {active_capacity} instances[/dim]\n")

            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=get_iac_root()
            )

            # Stream output
            for line in process.stdout:
                console.print(line, end="")

            process.wait()

            if process.returncode != 0:
                console.print(f"\n[red]Deployment failed with exit code {process.returncode}[/red]")
                return False

            console.print(f"\n[green]Deployment command completed![/green]\n")

            # Terminate celery-beat to force recreation with new image
            console.print(f"[bold cyan]Restarting Celery Beat with new image...[/bold cyan]\n")
            self._restart_celery_beat()

            # Monitor until healthy
            console.print(f"[bold cyan]Monitoring {target_env} environment health...[/bold cyan]\n")
            return self._monitor_deployment(target_env)

        except KeyboardInterrupt:
            console.print("\n[yellow]Deployment monitoring interrupted by user.[/yellow]")
            return False
        except Exception as e:
            console.print(f"\n[red]Deployment error: {e}[/red]")
            return False

    def _restart_celery_beat(self):
        """Terminate celery-beat instance to force recreation with new image."""
        try:
            # Get celery-beat instance ID
            beat_asg = "superschedules-prod-celery-beat-asg"
            asg_info = self.aws.get_asg_info(beat_asg)

            if not asg_info or not asg_info.get("Instances"):
                console.print("[dim]No celery-beat instance found, skipping restart[/dim]")
                return

            instance_id = asg_info["Instances"][0]["InstanceId"]
            console.print(f"[dim]Terminating celery-beat instance {instance_id}...[/dim]")

            # Terminate the instance - ASG will recreate it automatically
            self.aws.ec2.terminate_instances(InstanceIds=[instance_id])
            console.print("[green]✓ Celery-beat instance terminated (ASG will recreate with new image)[/green]\n")

        except Exception as e:
            console.print(f"[yellow]Warning: Failed to restart celery-beat: {e}[/yellow]")
            console.print("[dim]You may need to manually restart it later[/dim]\n")

    def _monitor_deployment(self, environment: str) -> bool:
        """Monitor deployment until healthy or timeout."""
        asg_name = self.config.blue_asg if environment == "blue" else self.config.green_asg
        target_groups = self.config.blue_target_groups if environment == "blue" else self.config.green_target_groups

        max_wait_time = 600  # 10 minutes
        check_interval = 10  # Check every 10 seconds
        elapsed = 0

        console.print(f"[dim]Waiting for {environment} to become healthy (timeout: {max_wait_time}s)...[/dim]\n")

        with Live(console=console, refresh_per_second=1) as live:
            while elapsed < max_wait_time:
                status = self.aws.get_environment_status(asg_name, target_groups)

                # Create status display
                status_text = Text()
                status_text.append(f"⏱  Elapsed: {elapsed}s / {max_wait_time}s\n\n", style="cyan")

                if not status["exists"] or status["desired_capacity"] == 0:
                    status_text.append("Status: ", style="white")
                    status_text.append("No instances\n", style="yellow")
                else:
                    # Instance status
                    status_text.append(f"Instances: {len(status['instances'])}\n", style="white")

                    for instance in status["instances"]:
                        state = instance["state"]
                        state_style = "green" if state == "running" else "yellow"
                        status_text.append(f"  • {instance['instance_id']}: ", style="dim")
                        status_text.append(f"{state}\n", style=state_style)

                    # Health status
                    status_text.append("\nHealth:\n", style="white")
                    all_healthy = True

                    for tg_name, tg_health in status["health"].items():
                        if not tg_health:
                            status_text.append(f"  • {tg_name}: ", style="dim")
                            status_text.append("no targets\n", style="yellow")
                            all_healthy = False
                            continue

                        # Count different health states
                        healthy_count = sum(1 for t in tg_health if t["TargetHealth"]["State"] == "healthy")
                        unused_count = sum(1 for t in tg_health if t["TargetHealth"]["State"] == "unused")
                        unhealthy_count = sum(1 for t in tg_health if t["TargetHealth"]["State"] == "unhealthy")
                        initial_count = sum(1 for t in tg_health if t["TargetHealth"]["State"] == "initial")
                        total_count = len(tg_health)

                        status_text.append(f"  ", style="dim")
                        if healthy_count == total_count:
                            # All healthy and receiving traffic
                            status_text.append(f"● ", style="green")
                            status_text.append(f"{tg_name}: ", style="bold white")
                            status_text.append(f"{healthy_count}/{total_count} ✓ receiving traffic\n", style="green")
                        elif unused_count == total_count:
                            # All unused - ready but not receiving traffic
                            status_text.append(f"○ ", style="cyan")
                            status_text.append(f"{tg_name}: ", style="bold white")
                            status_text.append(f"{unused_count}/{total_count} ✓ ready (not receiving traffic)\n", style="cyan")
                        elif initial_count > 0:
                            # Still initializing
                            status_text.append(f"◐ ", style="yellow")
                            status_text.append(f"{tg_name}: ", style="bold white")
                            status_text.append(f"{initial_count}/{total_count} initializing...\n", style="yellow")
                            all_healthy = False
                        elif unhealthy_count > 0:
                            # Some unhealthy
                            status_text.append(f"✗ ", style="red")
                            status_text.append(f"{tg_name}: ", style="bold white")
                            status_text.append(f"{unhealthy_count}/{total_count} failing checks\n", style="red")
                            all_healthy = False
                        else:
                            # Mixed state
                            status_text.append(f"◐ ", style="yellow")
                            status_text.append(f"{tg_name}: ", style="bold white")
                            status_text.append(f"mixed state\n", style="yellow")
                            all_healthy = False

                    # Check if ready
                    if all_healthy and len(status["instances"]) >= status["desired_capacity"]:
                        status_text.append("\n", style="white")
                        status_text.append("✓ Environment is healthy and ready!", style="bold green")
                        live.update(Panel(status_text, title=f"{environment.upper()} Deployment Status", border_style="green"))
                        console.print()
                        return True

                live.update(Panel(status_text, title=f"{environment.upper()} Deployment Status", border_style="cyan"))

                time.sleep(check_interval)
                elapsed += check_interval

        console.print("[red]Timeout waiting for environment to become healthy.[/red]")
        return False

    def flip_traffic(self, target_env: Optional[str] = None, skip_confirm: bool = False):
        """Flip traffic to specified environment or auto-detect inactive."""
        active_env = self.get_active_environment()
        active_capacity = self.get_active_capacity()

        if target_env is None:
            target_env = "green" if active_env == "blue" else "blue"

        console.print(f"\n[bold]Current active:[/bold] [cyan]{active_env.upper()}[/cyan]")
        console.print(f"[bold yellow]⚠ WARNING: This will switch production traffic to {target_env.upper()}![/bold yellow]\n")

        if not skip_confirm and not click.confirm(f"Are you sure you want to flip traffic to {target_env.upper()}?", default=False):
            console.print("[yellow]Traffic flip cancelled.[/yellow]")
            return False

        try:
            # Determine the correct make target based on target environment
            if target_env == "green":
                # Flip to green - preserve green's capacity (which will become active)
                # Echo 'y' to auto-confirm Makefile prompt (we already confirmed above)
                cmd = "echo 'y' | make deploy:flip"
            else:
                # Flip back to blue (rollback) - preserve blue's capacity (which will become active)
                # Echo 'y' to auto-confirm Makefile prompt (we already confirmed above)
                cmd = "echo 'y' | make deploy:rollback"

            console.print(f"\n[dim]Running: {cmd}[/dim]\n")

            result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True, cwd=get_iac_root())
            console.print(result.stdout)

            console.print(f"\n[green]✓ Traffic successfully flipped to {target_env.upper()}![/green]")
            return True

        except subprocess.CalledProcessError as e:
            console.print(f"\n[red]Traffic flip failed: {e}[/red]")
            if e.stderr:
                console.print(f"[red]{e.stderr}[/red]")
            return False

    def deploy_and_flip(self, wait_seconds: int = 30):
        """Deploy to inactive environment, wait, then flip traffic automatically."""
        active_env = self.get_active_environment()

        if active_env == "unknown":
            console.print("[red]Cannot determine active environment. Please check manually.[/red]")
            return False

        target_env = "green" if active_env == "blue" else "blue"

        console.print(f"\n[bold cyan]{'='*60}[/bold cyan]")
        console.print(f"[bold cyan]  DEPLOY AND FLIP - Automated Deployment[/bold cyan]")
        console.print(f"[bold cyan]{'='*60}[/bold cyan]\n")
        console.print(f"[bold]Current active:[/bold] [cyan]{active_env.upper()}[/cyan]")
        console.print(f"[bold]Will deploy to:[/bold] [cyan]{target_env.upper()}[/cyan]")
        console.print(f"[bold]Then flip traffic after {wait_seconds}s stabilization period[/bold]\n")

        # Deploy without confirmation
        success = self.deploy_to_inactive(skip_confirm=True)

        if not success:
            console.print("\n[red]Deployment failed. Aborting flip.[/red]")
            return False

        # Wait for stabilization
        console.print(f"\n[bold cyan]{'='*60}[/bold cyan]")
        console.print(f"[bold green]✓ Deployment healthy! Waiting {wait_seconds}s before flip...[/bold green]")
        console.print(f"[bold cyan]{'='*60}[/bold cyan]\n")

        for remaining in range(wait_seconds, 0, -1):
            console.print(f"\r[cyan]Flipping traffic in {remaining}s...[/cyan]  ", end="")
            time.sleep(1)

        console.print("\n")

        # Flip traffic without confirmation
        success = self.flip_traffic(target_env=target_env, skip_confirm=True)

        if success:
            console.print(f"\n[bold green]{'='*60}[/bold green]")
            console.print(f"[bold green]  ✓ DEPLOY AND FLIP COMPLETE![/bold green]")
            console.print(f"[bold green]  Traffic now routing to {target_env.upper()}[/bold green]")
            console.print(f"[bold green]{'='*60}[/bold green]\n")
        else:
            console.print(f"\n[bold red]Traffic flip failed after successful deployment.[/bold red]")
            console.print(f"[yellow]The new version is deployed to {target_env} but not receiving traffic.[/yellow]")
            console.print(f"[yellow]You can manually flip with: deploy-manager flip[/yellow]\n")

        return success


@click.group()
def cli():
    """Blue/Green Deployment Manager for Superschedules."""
    pass


@cli.command()
def dashboard():
    """Run interactive dashboard (default)."""
    from .interactive import InteractiveDashboard
    try:
        dash = InteractiveDashboard()
        dash.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Exited by user[/yellow]")


@cli.command()
def status():
    """Show current deployment status."""
    # Check if terraform is running
    try:
        result = subprocess.run(["pgrep", "-f", "terraform"], capture_output=True, text=True)
        if result.returncode == 0:
            console.print("[bold yellow]Warning: Terraform is currently running.[/bold yellow]")
            console.print("[dim]Status information may be incomplete or outdated.[/dim]\n")
    except Exception:
        pass  # Ignore if pgrep fails

    config = Config()
    manager = DeploymentManager(config)
    manager.show_status()


@cli.command()
def deploy():
    """Deploy to inactive environment and optionally flip traffic."""
    config = Config()
    manager = DeploymentManager(config)

    # Deploy to inactive environment
    success = manager.deploy_to_inactive()

    if not success:
        console.print("\n[red]Deployment did not complete successfully.[/red]")
        sys.exit(1)

    # Prompt for traffic flip
    console.print("\n" + "="*60)
    console.print("[bold green]Deployment is healthy and ready![/bold green]")
    console.print("="*60 + "\n")

    if click.confirm("Do you want to flip traffic to the new environment now?", default=False):
        manager.flip_traffic()
    else:
        console.print("\n[yellow]Traffic not flipped. You can flip manually later with:[/yellow]")
        console.print("[cyan]  deploy-manager flip[/cyan]\n")


@cli.command()
@click.option("--to", "target_env", type=click.Choice(["blue", "green"]), help="Target environment")
def flip(target_env):
    """Flip traffic between blue and green environments."""
    config = Config()
    manager = DeploymentManager(config)
    manager.flip_traffic(target_env)


@cli.command("deploy-and-flip")
@click.option("--wait", "wait_seconds", default=30, help="Seconds to wait after deploy before flip")
def deploy_and_flip(wait_seconds):
    """Deploy to inactive environment and automatically flip traffic.

    This is an automated workflow that:
    1. Deploys to the inactive environment
    2. Waits for it to become healthy
    3. Waits an additional stabilization period (default 30s)
    4. Automatically flips traffic to the new environment

    No confirmation prompts - fully automated.
    """
    config = Config()
    manager = DeploymentManager(config)
    success = manager.deploy_and_flip(wait_seconds=wait_seconds)
    if not success:
        sys.exit(1)


@cli.command("deploy-when-ready")
@click.option("--service", "-s", type=click.Choice(["api", "frontend", "all"]), default="all",
              help="Service to deploy (default: all)")
@click.option("--tag", "-t", default=None,
              help="Image tag to deploy (default: main-<current-git-sha>)")
@click.option("--timeout", default=1200, type=int,
              help="Timeout in seconds (default: 1200 = 20 min)")
@click.option("--no-flip", is_flag=True,
              help="Deploy but do not flip traffic")
def deploy_when_ready(service, tag, timeout, no_flip):
    """Wait for ECR image to be ready, then deploy.

    This command polls ECR until the specified image tag exists,
    then deploys it to the inactive environment.

    If no tag is provided, uses main-<current-git-sha> from the current directory.
    """
    ecr = ECRClient()
    state = DeployState()

    # Get tag from git if not provided
    if tag is None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True
            )
            git_sha = result.stdout.strip()
            tag = f"main-{git_sha}"
            console.print(f"[dim]Using tag from git: {tag}[/dim]")
        except Exception as e:
            console.print(f"[red]Error getting git SHA: {e}[/red]")
            console.print("[yellow]Please provide --tag explicitly[/yellow]")
            sys.exit(1)

    # Determine which repos to check
    repos_to_check = []
    if service in ["api", "all"]:
        repos_to_check.append(("api", ecr.get_repo_name("api")))
    if service in ["frontend", "all"]:
        repos_to_check.append(("frontend", ecr.get_repo_name("frontend")))

    console.print(f"\n[bold]Waiting for image tag: {tag}[/bold]")
    console.print(f"Timeout: {timeout}s ({timeout // 60} min)\n")

    # Wait for all required images
    all_ready = True
    for svc_name, repo_name in repos_to_check:
        console.print(f"[cyan]Checking {svc_name}[/cyan] ({repo_name})...")

        def progress_callback(attempt, elapsed, found):
            status = "[green]FOUND[/green]" if found else "[yellow]waiting...[/yellow]"
            console.print(f"  Attempt {attempt}, elapsed {elapsed}s: {status}", end="\r")

        ready = ecr.wait_for_image(repo_name, tag, timeout=timeout, callback=progress_callback)
        console.print()  # newline after progress

        if ready:
            console.print(f"  [green]✓ {svc_name} image ready[/green]")
        else:
            console.print(f"  [red]✗ {svc_name} image not found after {timeout}s[/red]")
            all_ready = False

    if not all_ready:
        console.print("\n[red]Aborting: Not all images are ready[/red]")
        sys.exit(1)

    # Deploy using make target
    console.print(f"\n[bold green]All images ready! Deploying...[/bold green]")

    iac_root = get_iac_root()
    result = subprocess.run(
        ["make", f"deploy:with-tag", f"TAG={tag}"],
        cwd=iac_root
    )

    if result.returncode != 0:
        console.print("[red]Deployment failed[/red]")
        sys.exit(1)

    # Record deployment
    state.record_deploy(tag, service)
    console.print(f"[green]✓ Deployment recorded to history[/green]")

    # Optionally flip traffic
    if not no_flip:
        console.print("\n[yellow]Waiting for new instances to become healthy...[/yellow]")
        console.print("[dim]Run 'deploy-manager flip' when ready to switch traffic[/dim]")


@cli.command("images")
@click.option("--service", "-s", type=click.Choice(["api", "frontend"]), default="api",
              help="Service to check (default: api)")
@click.option("--limit", "-n", default=10, type=int,
              help="Number of images to show (default: 10)")
def images(service, limit):
    """Show available images and currently deployed version."""
    ecr = ECRClient()
    state = DeployState()

    repo_name = ecr.get_repo_name(service)
    console.print(f"\n[bold]{repo_name}[/bold] images:\n")

    # Get deployed tag from state
    deployed_tag = state.get_current_tag()
    if deployed_tag:
        console.print(f"  [bold]Deployed:[/bold] {deployed_tag} [dim](from deploy history)[/dim]")
    else:
        console.print(f"  [bold]Deployed:[/bold] [dim]unknown[/dim]")

    console.print()

    # Get available images
    images_list = ecr.get_latest_images(repo_name, limit=limit, tag_prefix="main-")

    if not images_list:
        console.print("  [yellow]No main-* tagged images found[/yellow]")
        return

    table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
    table.add_column("Tag", style="cyan")
    table.add_column("Pushed", style="dim")
    table.add_column("Status")

    for img in images_list:
        # Find the main-* tag
        main_tag = None
        for t in img["tags"]:
            if t.startswith("main-"):
                main_tag = t
                break

        if not main_tag:
            continue

        # Format pushed time
        pushed_at = img["pushed_at"]
        if pushed_at:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            delta = now - pushed_at
            if delta.days > 0:
                pushed_str = f"{delta.days}d ago"
            elif delta.seconds > 3600:
                pushed_str = f"{delta.seconds // 3600}h ago"
            else:
                pushed_str = f"{delta.seconds // 60}m ago"
        else:
            pushed_str = "unknown"

        # Status indicator
        if main_tag == deployed_tag:
            status = "[green]← DEPLOYED[/green]"
        elif images_list.index(img) == 0 and main_tag != deployed_tag:
            status = "[yellow]← NEW[/yellow]"
        else:
            status = ""

        table.add_row(main_tag, pushed_str, status)

    console.print(table)


@cli.command("rollback")
@click.option("--to", "target_tag", default=None,
              help="Specific tag to rollback to (default: previous deployment)")
@click.option("--yes", "-y", is_flag=True,
              help="Skip confirmation prompt")
def rollback(target_tag, yes):
    """Rollback to a previous deployment.

    By default, rolls back to the previous deployed tag from history.
    Use --to to specify a specific tag to rollback to.
    """
    state = DeployState()
    ecr = ECRClient()

    # Get target tag
    if target_tag is None:
        target_tag = state.get_previous_tag()
        if not target_tag:
            console.print("[red]No previous deployment found in history[/red]")
            console.print("[dim]Use --to to specify a tag explicitly[/dim]")
            sys.exit(1)
        console.print(f"Rolling back to previous deployment: [cyan]{target_tag}[/cyan]")
    else:
        console.print(f"Rolling back to: [cyan]{target_tag}[/cyan]")

    # Verify image exists in ECR
    api_repo = ecr.get_repo_name("api")
    if not ecr.image_exists(api_repo, target_tag):
        console.print(f"[red]Image {target_tag} not found in ECR[/red]")
        console.print("[dim]The image may have been cleaned up by lifecycle policy[/dim]")
        sys.exit(1)

    console.print(f"[green]✓ Image exists in ECR[/green]")

    # Confirm
    if not yes:
        if not click.confirm("Proceed with rollback?"):
            console.print("Rollback cancelled")
            sys.exit(0)

    # Deploy the rollback tag
    console.print("\n[bold]Deploying rollback...[/bold]")

    iac_root = get_iac_root()
    result = subprocess.run(
        ["make", f"deploy:with-tag", f"TAG={target_tag}"],
        cwd=iac_root
    )

    if result.returncode != 0:
        console.print("[red]Rollback deployment failed[/red]")
        sys.exit(1)

    # Record deployment
    state.record_deploy(target_tag, "all")
    console.print(f"\n[green]✓ Rollback deployed successfully[/green]")
    console.print("[dim]Run 'deploy-manager flip' when ready to switch traffic[/dim]")


@cli.command("history")
@click.option("--limit", "-n", default=10, type=int,
              help="Number of entries to show (default: 10)")
def history(limit):
    """Show deployment history."""
    state = DeployState()

    history_list = state.get_history(limit=limit)

    if not history_list:
        console.print("[yellow]No deployment history found[/yellow]")
        return

    console.print("\n[bold]Deployment History[/bold]\n")

    table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
    table.add_column("#", style="dim")
    table.add_column("Tag", style="cyan")
    table.add_column("Service")
    table.add_column("When", style="dim")
    table.add_column("By")

    for i, deploy in enumerate(history_list):
        # Format timestamp
        ts = deploy.get("timestamp", "")
        if ts:
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                from datetime import timezone
                now = datetime.now(timezone.utc)
                delta = now - dt
                if delta.days > 0:
                    when = f"{delta.days}d ago"
                elif delta.seconds > 3600:
                    when = f"{delta.seconds // 3600}h ago"
                else:
                    when = f"{delta.seconds // 60}m ago"
            except Exception:
                when = ts[:19]
        else:
            when = "unknown"

        status = "[green]current[/green]" if i == 0 else str(i)
        table.add_row(
            status,
            deploy.get("tag", "?"),
            deploy.get("service", "all"),
            when,
            deploy.get("deployed_by", "?")
        )

    console.print(table)


# =============================================================================
# Prod-Lite Commands (non-Docker, fast deploys)
# =============================================================================

class ProdLiteManager:
    """Manages prod-lite deployments via SSM."""

    INSTANCE_NAME = "superschedules-prod-lite"
    REGION = "us-east-1"

    # Apps hosted on prod-lite instance
    APPS = {
        "superschedules": {
            "dir": "/opt/superschedules",
            "frontend_dir": "/opt/superschedules_frontend",
            "services": ["embedding", "gunicorn", "celery-worker", "celery-beat"],
            "has_frontend": True,
            "branch": "main",
        },
        "gkp-labs": {
            "dir": "/opt/gkp_labs",
            "frontend_dir": None,
            "services": ["gunicorn-gkplabs"],
            "has_frontend": False,
            "branch": "main",
        }
    }

    def __init__(self):
        import boto3
        self.ec2 = boto3.client("ec2", region_name=self.REGION)
        self.ssm = boto3.client("ssm", region_name=self.REGION)

    def get_instance(self) -> Optional[Dict]:
        """Get the prod-lite instance."""
        response = self.ec2.describe_instances(
            Filters=[
                {"Name": "tag:Name", "Values": [self.INSTANCE_NAME]},
                {"Name": "instance-state-name", "Values": ["running"]}
            ]
        )
        try:
            return response["Reservations"][0]["Instances"][0]
        except (IndexError, KeyError):
            return None

    def check_ssm_status(self, instance_id: str) -> bool:
        """Check if instance is SSM-managed."""
        response = self.ssm.describe_instance_information(
            Filters=[{"Key": "InstanceIds", "Values": [instance_id]}]
        )
        try:
            status = response["InstanceInformationList"][0]["PingStatus"]
            return status == "Online"
        except (IndexError, KeyError):
            return False

    def run_command(self, instance_id: str, command: str, timeout: int = 300) -> tuple[bool, str]:
        """Run a command via SSM and return (success, output)."""
        try:
            response = self.ssm.send_command(
                InstanceIds=[instance_id],
                DocumentName="AWS-RunShellScript",
                Parameters={"commands": [command]},
                TimeoutSeconds=timeout
            )
            command_id = response["Command"]["CommandId"]

            # Wait for command to complete
            import time
            for _ in range(timeout // 5):
                time.sleep(5)
                result = self.ssm.get_command_invocation(
                    CommandId=command_id,
                    InstanceId=instance_id
                )
                status = result["Status"]
                if status in ["Success", "Failed", "Cancelled", "TimedOut"]:
                    break

            output = result.get("StandardOutputContent", "")
            error = result.get("StandardErrorContent", "")
            success = result["Status"] == "Success"

            return success, output if success else error
        except Exception as e:
            return False, str(e)

    def deploy_app(self, instance_id: str, app_name: str) -> bool:
        """Deploy a specific app (gkp-labs or superschedules)."""
        if app_name not in self.APPS:
            console.print(f"[red]Unknown app: {app_name}[/red]")
            console.print(f"[dim]Available apps: {', '.join(self.APPS.keys())}[/dim]")
            return False

        app = self.APPS[app_name]
        app_dir = app["dir"]
        branch = app["branch"]
        services = app["services"]

        console.print(f"[bold magenta]Deploying {app_name}...[/bold magenta]\n")

        # Step 1: Update code
        console.print(f"[cyan]Updating {app_name} code...[/cyan]")
        cmd = f"""cd {app_dir} && \
            git fetch origin && \
            git reset --hard origin/{branch} && \
            chown -R www-data:www-data . && \
            echo 'Code updated'"""
        success, output = self.run_command(instance_id, cmd, timeout=120)
        if not success:
            console.print(f"[red]✗ Git failed:[/red] {output}")
            return False
        console.print(f"[green]✓ {app_name} code updated[/green]")

        # Step 2: Install deps & migrate
        console.print(f"[cyan]Installing dependencies & running migrations...[/cyan]")
        cmd = f"""cd {app_dir} && \
            sudo -u www-data bash -c 'source venv/bin/activate && set -a && source .env && set +a && \
                pip install -r requirements.txt -q && \
                python manage.py migrate --noinput && \
                python manage.py collectstatic --noinput -v0' && \
            echo 'Dependencies installed'"""
        success, output = self.run_command(instance_id, cmd, timeout=600)
        if not success:
            console.print(f"[red]✗ Dependencies/migrate failed:[/red] {output}")
            return False
        console.print(f"[green]✓ Dependencies installed[/green]")

        # Step 3: Restart services
        services_str = " ".join(services)
        console.print(f"[cyan]Restarting services ({services_str})...[/cyan]")
        cmd = f"sudo systemctl restart {services_str} && echo 'Services restarted'"
        success, output = self.run_command(instance_id, cmd, timeout=60)
        if not success:
            console.print(f"[red]✗ Service restart failed:[/red] {output}")
            return False
        console.print(f"[green]✓ Services restarted[/green]")

        console.print(f"\n[bold green]{app_name} deployment complete![/bold green]")
        return True


@cli.group()
def lite():
    """Prod-lite environment commands (non-Docker, fast deploys)."""
    pass


@lite.command("status")
def lite_status():
    """Show prod-lite instance status."""
    manager = ProdLiteManager()
    instance = manager.get_instance()

    if not instance:
        console.print("[red]No running prod-lite instance found.[/red]")
        console.print("[dim]Run 'make prod-lite-apply' to create one.[/dim]")
        return

    instance_id = instance["InstanceId"]
    public_ip = instance.get("PublicIpAddress", "N/A")
    launch_time = instance.get("LaunchTime", "N/A")
    instance_type = instance.get("InstanceType", "N/A")

    ssm_status = "Online" if manager.check_ssm_status(instance_id) else "Offline"

    # Create status table
    table = Table(title="Prod-Lite Instance", box=box.ROUNDED)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Instance ID", instance_id)
    table.add_row("Public IP", public_ip)
    table.add_row("Instance Type", instance_type)
    table.add_row("Launch Time", str(launch_time))
    table.add_row("SSM Status", f"[green]{ssm_status}[/green]" if ssm_status == "Online" else f"[red]{ssm_status}[/red]")

    console.print(table)

    # Show URLs
    console.print("\n[bold]URLs:[/bold]")
    console.print("  API:      https://api.eventzombie.com")
    console.print("  Frontend: https://www.eventzombie.com")
    console.print("  Admin:    https://admin.eventzombie.com")

    # Show connect command
    console.print(f"\n[bold]Connect via SSM:[/bold]")
    console.print(f"  deploy-manager lite shell              # Interactive bash (as www-data)")
    console.print(f"  deploy-manager lite shell --root       # Interactive bash (as root)")
    console.print(f"  aws ssm start-session --target {instance_id} --region {manager.REGION}")


@lite.command("deploy")
@click.option("--service", "-s", type=click.Choice(["backend", "frontend", "all"]), default="all",
              help="Which service to deploy (for superschedules)")
@click.option("--app", "-a", type=click.Choice(["superschedules", "gkp-labs", "all"]), default="superschedules",
              help="Which app to deploy")
def lite_deploy(service, app):
    """Deploy to prod-lite via SSM (fast ~30s deploy).

    By default, deploys superschedules. Use --app to specify a different app:

    \b
      deploy-manager lite deploy                    # Deploy superschedules (default)
      deploy-manager lite deploy --app gkp-labs    # Deploy GKP Labs
      deploy-manager lite deploy --app all         # Deploy all apps
    """
    manager = ProdLiteManager()
    instance = manager.get_instance()

    if not instance:
        console.print("[red]No running prod-lite instance found.[/red]")
        sys.exit(1)

    instance_id = instance["InstanceId"]

    if not manager.check_ssm_status(instance_id):
        console.print("[red]Instance is not SSM-managed or not online yet.[/red]")
        console.print("[dim]Wait a few minutes for the instance to register with SSM.[/dim]")
        sys.exit(1)

    # Handle GKP Labs deployment
    if app == "gkp-labs":
        success = manager.deploy_app(instance_id, "gkp-labs")
        if not success:
            sys.exit(1)
        return

    # Handle "all" apps deployment
    if app == "all":
        console.print("[bold cyan]Deploying all apps...[/bold cyan]\n")

        # Deploy superschedules first (with frontend)
        console.print("[bold]1/2 Deploying superschedules...[/bold]")
        # Fall through to superschedules deployment below

        # We'll deploy gkp-labs after superschedules
        deploy_gkplabs_after = True
    else:
        deploy_gkplabs_after = False

    # Original superschedules deployment logic
    console.print(f"[bold]Deploying {service} to prod-lite (superschedules)...[/bold]\n")

    if service == "all":
        # Deploy both backend and frontend, then restart once at the end
        console.print("[cyan]Updating backend code...[/cyan]")
        cmd = """cd /opt/superschedules && \
            git fetch origin && \
            git reset --hard origin/main && \
            chown -R www-data:www-data . && \
            echo 'Backend code updated'"""
        success, output = manager.run_command(instance_id, cmd, timeout=120)
        if not success:
            console.print(f"[red]✗ Backend git failed:[/red] {output}")
            sys.exit(1)
        console.print("[green]✓ Backend code updated[/green]")

        console.print("[cyan]Updating frontend code...[/cyan]")
        cmd = """cd /opt/superschedules_frontend && \
            git fetch origin && \
            git reset --hard origin/main && \
            chown -R www-data:www-data . && \
            echo 'Frontend code updated'"""
        success, output = manager.run_command(instance_id, cmd, timeout=120)
        if not success:
            console.print(f"[red]✗ Frontend git failed:[/red] {output}")
            sys.exit(1)
        console.print("[green]✓ Frontend code updated[/green]")

        console.print("[cyan]Installing backend dependencies & running migrations...[/cyan]")
        cmd = """cd /opt/superschedules && \
            sudo -u www-data bash -c 'source venv/bin/activate && set -a && source .env && set +a && \
                pip install -r requirements-prod.txt -q && \
                python manage.py migrate --noinput && \
                python manage.py collectstatic --noinput -v0' && \
            echo 'Backend deps installed'"""
        success, output = manager.run_command(instance_id, cmd, timeout=600)
        if not success:
            console.print(f"[red]✗ Backend deps/migrate failed:[/red] {output}")
            sys.exit(1)
        console.print("[green]✓ Backend dependencies installed[/green]")

        console.print("[cyan]Building frontend...[/cyan]")
        cmd = """cd /opt/superschedules_frontend && \
            sudo -u www-data bash -c 'pnpm install --frozen-lockfile 2>/dev/null || pnpm install' && \
            sudo -u www-data pnpm build && \
            echo 'Frontend built'"""
        success, output = manager.run_command(instance_id, cmd, timeout=600)
        if not success:
            console.print(f"[red]✗ Frontend build failed:[/red] {output}")
            sys.exit(1)
        console.print("[green]✓ Frontend built[/green]")

        console.print("[cyan]Restarting services...[/cyan]")
        cmd = "sudo systemctl restart embedding gunicorn celery-worker celery-beat && echo 'Services restarted'"
        success, output = manager.run_command(instance_id, cmd, timeout=60)
        if not success:
            console.print(f"[red]✗ Service restart failed:[/red] {output}")
            sys.exit(1)
        console.print("[green]✓ Services restarted[/green]")

    elif service == "backend":
        console.print("[cyan]Deploying backend...[/cyan]")
        cmd = """cd /opt/superschedules && \
            git fetch origin && \
            git reset --hard origin/main && \
            chown -R www-data:www-data . && \
            sudo -u www-data bash -c 'source venv/bin/activate && set -a && source .env && set +a && \
                pip install -r requirements-prod.txt -q && \
                python manage.py migrate --noinput && \
                python manage.py collectstatic --noinput -v0' && \
            sudo systemctl restart embedding gunicorn celery-worker celery-beat && \
            echo 'Backend deploy complete'"""
        success, output = manager.run_command(instance_id, cmd, timeout=600)
        if success:
            console.print(f"[green]✓ Backend deployed[/green]")
        else:
            console.print(f"[red]✗ Backend deploy failed:[/red] {output}")
            sys.exit(1)

    elif service == "frontend":
        console.print("[cyan]Deploying frontend...[/cyan]")
        cmd = """cd /opt/superschedules_frontend && \
            git fetch origin && \
            git reset --hard origin/main && \
            chown -R www-data:www-data . && \
            sudo -u www-data bash -c 'pnpm install --frozen-lockfile 2>/dev/null || pnpm install' && \
            sudo -u www-data pnpm build && \
            echo 'Frontend deploy complete'"""
        success, output = manager.run_command(instance_id, cmd, timeout=600)
        if success:
            console.print(f"[green]✓ Frontend deployed[/green]")
        else:
            console.print(f"[red]✗ Frontend deploy failed:[/red] {output}")
            sys.exit(1)

    console.print("\n[bold green]Superschedules deployment complete![/bold green]")

    # Deploy GKP Labs if --app all was specified
    if deploy_gkplabs_after:
        console.print("\n[bold]2/2 Deploying gkp-labs...[/bold]")
        success = manager.deploy_app(instance_id, "gkp-labs")
        if not success:
            console.print("[yellow]Warning: GKP Labs deployment failed, but superschedules deployed successfully.[/yellow]")
        else:
            console.print("\n[bold green]All apps deployed successfully![/bold green]")


@lite.command("shell")
@click.option("--root", "-r", is_flag=True, help="Start as root (default starts bash as www-data)")
def lite_shell(root):
    """Open interactive SSM session to prod-lite instance.

    Starts a bash shell on the prod-lite instance via SSM (no SSH keys needed).
    By default runs as www-data user in /opt/superschedules.

    \b
    Common uses:
      - Run Django management commands (e.g., createsuperuser, shell_plus)
      - Debug issues on the instance
      - Check logs in /var/log/superschedules/

    \b
    Examples:
      deploy-manager lite shell                # Shell as www-data
      deploy-manager lite shell --root         # Shell as root
    """
    manager = ProdLiteManager()
    instance = manager.get_instance()

    if not instance:
        console.print("[red]No running prod-lite instance found.[/red]")
        sys.exit(1)

    instance_id = instance["InstanceId"]

    if root:
        console.print(f"[cyan]Starting bash session to {instance_id} (as root)...[/cyan]")
        shell_cmd = "cd /opt/superschedules && bash -l"
    else:
        console.print(f"[cyan]Starting bash session to {instance_id} (as www-data)...[/cyan]")
        shell_cmd = "cd /opt/superschedules && sudo -u www-data bash -l"

    import os
    os.execvp("aws", [
        "aws", "ssm", "start-session",
        "--target", instance_id,
        "--region", manager.REGION,
        "--document-name", "AWS-StartInteractiveCommand",
        "--parameters", f"command={shell_cmd}"
    ])


@lite.command("logs")
@click.option("--service", "-s", type=click.Choice(["gunicorn", "celery", "nginx", "all"]), default="all",
              help="Which service logs to tail")
@click.option("--follow", "-f", is_flag=True, help="Follow logs in real-time")
def lite_logs(service, follow):
    """Tail CloudWatch logs from prod-lite."""
    log_group = "/aws/superschedules/prod-lite/app"

    cmd = ["aws", "logs", "tail", log_group, "--region", "us-east-1"]

    if follow:
        cmd.append("--follow")

    # Filter by service if specified
    if service != "all":
        stream_map = {
            "gunicorn": "gunicorn-error",
            "celery": "celery-worker",
            "nginx": "nginx-error"
        }
        cmd.extend(["--log-stream-names", stream_map.get(service, service)])

    console.print(f"[cyan]Tailing logs from {log_group}...[/cyan]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    import os
    os.execvp("aws", cmd)


@lite.command("services")
def lite_services():
    """Check status of services on prod-lite instance."""
    manager = ProdLiteManager()
    instance = manager.get_instance()

    if not instance:
        console.print("[red]No running prod-lite instance found.[/red]")
        sys.exit(1)

    instance_id = instance["InstanceId"]

    if not manager.check_ssm_status(instance_id):
        console.print("[red]Instance is not SSM-managed.[/red]")
        sys.exit(1)

    console.print("[cyan]Checking services...[/cyan]\n")

    cmd = """for svc in embedding gunicorn celery-worker celery-beat nginx; do
        status=$(systemctl is-active $svc 2>/dev/null || echo 'inactive')
        echo "$svc: $status"
    done"""

    success, output = manager.run_command(instance_id, cmd, timeout=30)

    if success:
        table = Table(title="Service Status", box=box.ROUNDED)
        table.add_column("Service", style="cyan")
        table.add_column("Status", style="white")

        for line in output.strip().split("\n"):
            if ": " in line:
                svc, status = line.split(": ", 1)
                status_style = "[green]active[/green]" if status.strip() == "active" else f"[red]{status.strip()}[/red]"
                table.add_row(svc, status_style)

        console.print(table)
    else:
        console.print(f"[red]Failed to check services:[/red] {output}")


@lite.command("restart")
@click.option("--service", "-s", type=click.Choice(["gunicorn", "celery", "embedding", "all"]), default="all",
              help="Which service to restart")
def lite_restart(service):
    """Restart services without deploying (no git pull/build)."""
    manager = ProdLiteManager()
    instance = manager.get_instance()

    if not instance:
        console.print("[red]No running prod-lite instance found.[/red]")
        sys.exit(1)

    instance_id = instance["InstanceId"]

    if not manager.check_ssm_status(instance_id):
        console.print("[red]Instance is not SSM-managed.[/red]")
        sys.exit(1)

    services_map = {
        "gunicorn": ["gunicorn"],
        "celery": ["celery-worker", "celery-beat"],
        "embedding": ["embedding"],
        "all": ["embedding", "gunicorn", "celery-worker", "celery-beat"]
    }

    services_to_restart = services_map[service]
    services_str = " ".join(services_to_restart)

    console.print(f"[cyan]Restarting {services_str}...[/cyan]")

    cmd = f"sudo systemctl restart {services_str} && echo 'Services restarted successfully'"

    success, output = manager.run_command(instance_id, cmd, timeout=60)

    if success:
        console.print(f"[green]✓ Restarted: {services_str}[/green]")
    else:
        console.print(f"[red]✗ Failed to restart services:[/red] {output}")
        sys.exit(1)


@lite.command("ami")
@click.option("--name", "-n", help="Custom AMI name (default: auto-generated with timestamp)")
@click.option("--no-reboot", is_flag=True, help="Create AMI without rebooting instance")
def lite_ami(name, no_reboot):
    """Create an AMI from the current prod-lite instance for faster launches."""
    import boto3
    from datetime import datetime

    manager = ProdLiteManager()
    instance = manager.get_instance()

    if not instance:
        console.print("[red]No running prod-lite instance found.[/red]")
        sys.exit(1)

    instance_id = instance["InstanceId"]

    # Generate AMI name if not provided
    if not name:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        name = f"superschedules-prod-lite-{timestamp}"

    console.print(f"[cyan]Creating AMI from {instance_id}...[/cyan]")
    console.print(f"  Name: {name}")
    console.print(f"  No-reboot: {no_reboot}")

    if not no_reboot:
        console.print("[yellow]⚠ Instance will be rebooted during AMI creation[/yellow]")
        if not click.confirm("Continue?", default=True):
            console.print("[dim]Cancelled[/dim]")
            return

    ec2 = boto3.client("ec2", region_name=manager.REGION)

    try:
        response = ec2.create_image(
            InstanceId=instance_id,
            Name=name,
            Description=f"Superschedules prod-lite AMI created from {instance_id}",
            NoReboot=no_reboot,
            TagSpecifications=[
                {
                    "ResourceType": "image",
                    "Tags": [
                        {"Key": "Name", "Value": name},
                        {"Key": "Environment", "Value": "prod-lite"},
                        {"Key": "SourceInstance", "Value": instance_id},
                        {"Key": "CreatedBy", "Value": "deploy-manager"}
                    ]
                }
            ]
        )

        ami_id = response["ImageId"]
        console.print(f"\n[green]✓ AMI creation started![/green]")
        console.print(f"  AMI ID: [bold]{ami_id}[/bold]")
        console.print(f"\n[dim]AMI will be available in a few minutes. Check status with:[/dim]")
        console.print(f"  aws ec2 describe-images --image-ids {ami_id} --query 'Images[0].State'")

        console.print(f"\n[dim]To use this AMI, update terraform/prod-lite/compute.tf:[/dim]")
        console.print(f'  ami_id = "{ami_id}"')

    except Exception as e:
        console.print(f"[red]✗ Failed to create AMI:[/red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
