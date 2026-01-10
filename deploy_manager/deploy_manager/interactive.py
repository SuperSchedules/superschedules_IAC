"""Interactive TUI for deployment management."""
import time
import subprocess
from datetime import datetime
from typing import Optional
import click
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from rich.align import Align

from .aws_client import AWSClient
from .config import Config
from .cli import DeploymentManager, get_iac_root
from .ecr_client import ECRClient
from .deploy_state import DeployState


console = Console()


def check_terraform_running() -> bool:
    """Check if there's a terraform process currently running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "terraform"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0  # 0 means process found
    except Exception:
        # If pgrep fails, assume no terraform running
        return False


class InteractiveDashboard:
    """Interactive dashboard for deployment management."""

    def __init__(self):
        self.config = Config()
        self.manager = DeploymentManager(self.config)
        self.aws = AWSClient(region=self.config.region)
        self.ecr = ECRClient(region=self.config.region)
        self.deploy_state = DeployState(region=self.config.region)
        self.selected_action = 0
        self.actions = [
            ("Deploy to Inactive Environment", "deploy"),
            ("Deploy and Flip (auto)", "deploy_and_flip"),
            ("Flip Traffic", "flip"),
            ("Scale Down Inactive", "scale_down"),
            ("Refresh Status", "refresh"),
            ("Exit", "exit")
        ]
        self.last_update = None
        self.message = None
        self.message_type = "info"  # info, success, error

    def create_header(self) -> Panel:
        """Create header panel."""
        header = Text()
        header.append("🚀 Superschedules Deployment Manager", style="bold cyan")
        header.append(f"\nLast updated: {datetime.now().strftime('%H:%M:%S')}", style="dim")
        if self.message:
            header.append("\n")
            style = {
                "info": "cyan",
                "success": "green",
                "error": "red"
            }.get(self.message_type, "white")
            header.append(f"\n{self.message}", style=f"bold {style}")
        return Panel(header, box=box.DOUBLE)

    def create_status_panels(self) -> Group:
        """Create status panels for both environments."""
        active_env = self.manager.get_active_environment()

        # Get status for both environments
        blue_status = self.aws.get_environment_status(
            self.config.blue_asg,
            self.config.blue_target_groups
        )
        green_status = self.aws.get_environment_status(
            self.config.green_asg,
            self.config.green_target_groups
        )

        # Create panels
        blue_panel = self._create_env_panel("Blue", blue_status, active_env == "blue")
        green_panel = self._create_env_panel("Green", green_status, active_env == "green")

        # Celery Beat status
        beat_status = self.aws.get_celery_beat_status()
        beat_panel = self._create_celery_beat_panel(beat_status)

        # Cost summary (include celery-beat)
        total_cost = blue_status.get("total_hourly_cost", 0) + green_status.get("total_hourly_cost", 0) + beat_status.get("hourly_cost", 0)
        cost_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        cost_table.add_row("Hourly:", f"[green]${total_cost:.4f}/hr[/green]")
        cost_table.add_row("Daily:", f"[green]${total_cost * 24:.2f}/day[/green]")
        cost_table.add_row("Monthly:", f"[green]${total_cost * 730:.2f}/mo[/green]")
        cost_panel = Panel(
            cost_table,
            title="💰 Cost Summary",
            border_style="green",
            box=box.ROUNDED
        )

        # Version info panel
        version_panel = self._create_version_panel()

        return Group(blue_panel, green_panel, beat_panel, version_panel, cost_panel)

    def _create_env_panel(self, name: str, status: dict, is_active: bool) -> Panel:
        """Create panel for single environment."""
        color = "blue" if name == "Blue" else "green"
        title = f"{name} Environment"
        if is_active:
            title += " ⭐ ACTIVE"

        if not status["exists"] or status["desired_capacity"] == 0:
            content = Text("No instances running", style="dim yellow")
            return Panel(content, title=title, border_style=color, box=box.ROUNDED)

        # Build content
        lines = []

        # Capacity
        lines.append(Text(f"Capacity: {status['desired_capacity']} ", style="white"))
        lines[-1].append(f"(min: {status['min_size']}, max: {status['max_size']})", style="dim")

        # Instances
        if status["instances"]:
            for instance in status["instances"]:
                uptime = instance["uptime"]
                uptime_str = f"{uptime['days']}d {uptime['hours']}h {uptime['minutes']}m"
                lifecycle = "Spot" if instance["lifecycle"] == "spot" else "On-Demand"
                lifecycle_style = "yellow" if instance["lifecycle"] == "spot" else "blue"

                state = instance["state"]
                state_style = "green" if state == "running" else "yellow"

                line = Text()
                line.append(f"\n  • {instance['instance_id']}: ", style="dim")
                line.append(f"{instance['instance_type']} ", style="white")
                line.append(f"{lifecycle} ", style=lifecycle_style)
                line.append(f"{state} ", style=state_style)
                line.append(f"↑{uptime_str} ", style="dim")
                line.append(f"${instance['hourly_cost']:.4f}/hr", style="green")
                lines.append(line)

        # Health - show both health state and traffic routing
        lines.append(Text())  # Empty line
        for tg_name, tg_health in status["health"].items():
            if not tg_health:
                health_line = Text("  • ", style="dim")
                health_line.append(f"{tg_name}: ", style="bold white")
                health_line.append("no targets", style="yellow")
                lines.append(health_line)
                continue

            # Count different health states
            healthy_count = sum(1 for t in tg_health if t["TargetHealth"]["State"] == "healthy")
            unused_count = sum(1 for t in tg_health if t["TargetHealth"]["State"] == "unused")
            unhealthy_count = sum(1 for t in tg_health if t["TargetHealth"]["State"] == "unhealthy")
            initial_count = sum(1 for t in tg_health if t["TargetHealth"]["State"] == "initial")
            total_count = len(tg_health)

            health_line = Text()
            if healthy_count == total_count:
                # All healthy and receiving traffic (active environment)
                health_line.append("  ● ", style="green")
                health_line.append(f"{tg_name}: ", style="bold white")
                health_line.append(f"{healthy_count}/{total_count} ✓ receiving traffic", style="green")
            elif unused_count == total_count:
                # All unused - ready but not receiving traffic (inactive environment)
                health_line.append("  ○ ", style="cyan")
                health_line.append(f"{tg_name}: ", style="bold white")
                health_line.append(f"{unused_count}/{total_count} ✓ ready (not receiving traffic)", style="cyan")
            elif initial_count > 0:
                # Still initializing
                health_line.append("  ◐ ", style="yellow")
                health_line.append(f"{tg_name}: ", style="bold white")
                health_line.append(f"{initial_count}/{total_count} initializing...", style="yellow")
            elif unhealthy_count > 0:
                # Some unhealthy
                health_line.append("  ✗ ", style="red")
                health_line.append(f"{tg_name}: ", style="bold white")
                health_line.append(f"{unhealthy_count}/{total_count} failing checks", style="red")
            else:
                # Mixed state
                health_line.append("  ◐ ", style="yellow")
                health_line.append(f"{tg_name}: ", style="bold white")
                health_line.append(f"mixed state", style="yellow")

            lines.append(health_line)

        # Cost
        cost_line = Text(f"\n\n💰 Cost: ", style="white")
        cost_line.append(f"${status['total_hourly_cost']:.4f}/hr", style="green")
        cost_line.append(f" (${status['total_monthly_cost']:.2f}/mo est)", style="dim green")
        lines.append(cost_line)

        return Panel(Group(*lines), title=title, border_style=color, box=box.ROUNDED)

    def _create_celery_beat_panel(self, status: dict) -> Panel:
        """Create panel for Celery Beat instance."""
        title = "⏰ Celery Beat (Scheduler)"

        if not status.get("exists") or not status.get("instance"):
            content = Text("No instance running", style="dim yellow")
            return Panel(content, title=title, border_style="yellow", box=box.ROUNDED)

        instance = status["instance"]
        lines = []

        # Instance info
        uptime = instance["uptime"]
        uptime_str = f"{uptime['days']}d {uptime['hours']}h {uptime['minutes']}m"
        lifecycle = "Spot" if instance["lifecycle"] == "spot" else "On-Demand"
        lifecycle_style = "yellow" if instance["lifecycle"] == "spot" else "blue"

        state = instance["state"]
        state_style = "green" if state == "running" else "yellow"

        line = Text()
        line.append(f"  • {instance['instance_id']}: ", style="dim")
        line.append(f"{instance['instance_type']} ", style="white")
        line.append(f"{lifecycle} ", style=lifecycle_style)
        line.append(f"{state} ", style=state_style)
        line.append(f"↑{uptime_str} ", style="dim")
        line.append(f"${instance['hourly_cost']:.4f}/hr", style="green")
        lines.append(line)

        # Status indicator
        status_line = Text("\n  ")
        if state == "running":
            status_line.append("● ", style="green")
            status_line.append("Scheduling tasks", style="green")
        else:
            status_line.append("◐ ", style="yellow")
            status_line.append("Starting...", style="yellow")
        lines.append(status_line)

        # Cost
        cost_line = Text(f"\n💰 Cost: ", style="white")
        cost_line.append(f"${status['hourly_cost']:.4f}/hr", style="green")
        cost_line.append(f" (${status['monthly_cost']:.2f}/mo est)", style="dim green")
        lines.append(cost_line)

        return Panel(Group(*lines), title=title, border_style="yellow", box=box.ROUNDED)

    def _create_version_panel(self) -> Panel:
        """Create panel showing deployed vs available versions."""
        title = "📦 Image Versions"
        lines = []

        try:
            # Get deployed tag from state
            deployed_tag = self.deploy_state.get_current_tag()

            # Get latest available images from ECR
            api_images = self.ecr.get_latest_images("superschedules-api", limit=3, tag_prefix="main-")

            # Deployed version
            deployed_line = Text("  Deployed: ", style="bold white")
            if deployed_tag:
                deployed_line.append(deployed_tag[:50], style="cyan")
            else:
                deployed_line.append("unknown", style="dim")
            lines.append(deployed_line)

            # Latest available
            if api_images:
                latest_tag = None
                for t in api_images[0].get("tags", []):
                    if t.startswith("main-"):
                        latest_tag = t
                        break

                latest_line = Text("  Available: ", style="bold white")
                if latest_tag:
                    if latest_tag == deployed_tag:
                        latest_line.append(latest_tag[:50], style="green")
                        latest_line.append(" ✓ up to date", style="dim green")
                    else:
                        latest_line.append(latest_tag[:50], style="yellow")
                        latest_line.append(" ← NEW", style="bold yellow")
                else:
                    latest_line.append("none", style="dim")
                lines.append(latest_line)

                # Pushed time
                pushed_at = api_images[0].get("pushed_at")
                if pushed_at:
                    from datetime import timezone
                    now = datetime.now(timezone.utc)
                    delta = now - pushed_at
                    if delta.days > 0:
                        pushed_str = f"{delta.days}d ago"
                    elif delta.seconds > 3600:
                        pushed_str = f"{delta.seconds // 3600}h ago"
                    else:
                        pushed_str = f"{delta.seconds // 60}m ago"
                    pushed_line = Text(f"  Last push: ", style="dim")
                    pushed_line.append(pushed_str, style="dim")
                    lines.append(pushed_line)
            else:
                lines.append(Text("  Available: no main-* images found", style="dim yellow"))

        except Exception as e:
            lines.append(Text(f"  Error loading version info: {str(e)[:40]}", style="dim red"))

        return Panel(Group(*lines), title=title, border_style="magenta", box=box.ROUNDED)

    def create_menu(self) -> Panel:
        """Create interactive menu."""
        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        table.add_column("Key", style="cyan", width=5)
        table.add_column("Action", style="white")

        for idx, (action_name, _) in enumerate(self.actions):
            key = str(idx + 1)
            if idx == self.selected_action:
                table.add_row(f"[bold cyan]{key}[/bold cyan]", f"[bold white]▶ {action_name}[/bold white]")
            else:
                table.add_row(key, action_name)

        help_text = Text("\nPress number key to select action, or 'q' to quit", style="dim")
        content = Group(table, help_text)

        return Panel(content, title="🎛️  Actions", border_style="cyan", box=box.ROUNDED)

    def create_layout(self) -> Layout:
        """Create the main layout."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=5),
            Layout(name="status", ratio=2),
            Layout(name="menu", size=len(self.actions) + 5)
        )

        layout["header"].update(self.create_header())
        layout["status"].update(self.create_status_panels())
        layout["menu"].update(self.create_menu())

        return layout

    def set_message(self, message: str, message_type: str = "info"):
        """Set a status message."""
        self.message = message
        self.message_type = message_type

    def clear_message(self):
        """Clear status message."""
        self.message = None

    def run_action(self, action_key: str) -> bool:
        """Run selected action. Returns False to exit."""
        self.clear_message()

        if action_key == "exit":
            return False

        if action_key == "refresh":
            self.set_message("Status refreshed", "success")
            return True

        if action_key == "deploy":
            # Exit live display for deployment
            console.clear()
            console.print("[bold cyan]Starting deployment...[/bold cyan]\n")
            success = self.manager.deploy_to_inactive()
            if success:
                console.print("\n[green]Press any key to return to dashboard...[/green]")
            else:
                console.print("\n[red]Press any key to return to dashboard...[/red]")
            input()
            return True

        if action_key == "deploy_and_flip":
            # Deploy to inactive, wait 30s, then flip - all automatic
            console.clear()
            success = self.manager.deploy_and_flip(wait_seconds=30)
            if success:
                console.print("\n[green]Press any key to return to dashboard...[/green]")
            else:
                console.print("\n[red]Press any key to return to dashboard...[/red]")
            input()
            return True

        if action_key == "flip":
            console.clear()
            console.print("[bold cyan]Flipping traffic...[/bold cyan]\n")
            success = self.manager.flip_traffic()
            if success:
                console.print("\n[green]Press any key to return to dashboard...[/green]")
            else:
                console.print("\n[red]Press any key to return to dashboard...[/red]")
            input()
            return True

        if action_key == "scale_down":
            active_env = self.manager.get_active_environment()
            inactive_env = "green" if active_env == "blue" else "blue"
            active_capacity = self.manager.get_active_capacity()

            console.clear()
            console.print(f"[bold yellow]Scale down {inactive_env.upper()} environment?[/bold yellow]\n")
            console.print(f"[dim]Will scale {inactive_env} to 0 and preserve {active_env}'s capacity at {active_capacity}[/dim]\n")

            if not click.confirm(f"This will set {inactive_env} to 0 instances", default=True):
                self.set_message("Scale down cancelled", "info")
                return True

            try:
                import subprocess
                cmd = f"make deploy:scale-down-{inactive_env} ACTIVE_DESIRED_CAPACITY={active_capacity}"
                result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True, cwd=get_iac_root())
                console.print(result.stdout)
                console.print(f"\n[green]✓ {inactive_env.upper()} scaled down successfully![/green]")
                console.print(f"[green]✓ {active_env.upper()} capacity preserved at {active_capacity}[/green]")
                console.print("\nPress any key to return to dashboard...")
                input()
                self.set_message(f"{inactive_env.upper()} scaled down", "success")
            except Exception as e:
                console.print(f"\n[red]Error: {e}[/red]")
                console.print("\nPress any key to return to dashboard...")
                input()
                self.set_message(f"Failed to scale down {inactive_env}", "error")

            return True

        return True

    def run(self):
        """Run the interactive dashboard."""
        # Check for running terraform before starting
        if check_terraform_running():
            console.print("[bold red]Error: Terraform is currently running![/bold red]")
            console.print("[yellow]Please wait for the current terraform operation to complete before using the dashboard.[/yellow]")
            console.print("[dim]Hint: Check for running deployments or terraform apply commands.[/dim]")
            return

        console.clear()

        while True:
            # Display the dashboard
            console.clear()
            console.print(self.create_header())
            console.print()
            status_panels = self.create_status_panels()
            console.print(status_panels)
            console.print()
            console.print(self.create_menu())
            console.print()

            # Get user input
            try:
                choice = console.input("[bold cyan]Select action (1-6, or 'q' to quit): [/bold cyan]").strip().lower()

                if choice == 'q':
                    break

                if choice == 'r':
                    self.set_message("Status refreshed", "success")
                    continue

                if choice.isdigit():
                    action_idx = int(choice) - 1
                    if 0 <= action_idx < len(self.actions):
                        _, action_key = self.actions[action_idx]
                        if not self.run_action(action_key):
                            break
                    else:
                        self.set_message(f"Invalid choice. Please select 1-{len(self.actions)}.", "error")
                else:
                    self.set_message("Invalid input. Please enter a number or 'q'.", "error")

            except KeyboardInterrupt:
                break
            except EOFError:
                break


@click.command()
def interactive():
    """Run interactive deployment dashboard."""
    try:
        dashboard = InteractiveDashboard()
        dashboard.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Exited by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        raise
