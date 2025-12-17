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


if __name__ == "__main__":
    cli()
