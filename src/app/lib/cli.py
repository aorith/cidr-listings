import asyncio

import click
from click import Group
from litestar import Litestar
from litestar.plugins import CLIPluginProtocol

from app.domain.auth.services import create_user as create_user_service
from app.domain.auth.services import reset_password as reset_password_service
from app.lib.db.migrations import run_migrations_from_cli


def _run_task(coro) -> None:
    loop = asyncio.new_event_loop()
    task = loop.create_task(coro)  # noqa: F841
    pending = asyncio.all_tasks(loop=loop)
    group = asyncio.gather(*pending)
    loop.run_until_complete(group)
    loop.close()


class CLIPlugin(CLIPluginProtocol):
    def on_cli_init(self, cli: Group) -> None:
        @cli.command()
        def is_debug_mode(app: Litestar):
            if app.debug:
                click.echo("App IS running in Debug mode.")
            else:
                click.echo("App is NOT running in Debug mode.")

        @cli.command(name="run-db-migrations", help="Run DB Migrations")
        def run_db_migrations() -> None:
            click.echo("Running DB migrations...")
            _run_task(run_migrations_from_cli())

        @cli.command(name="create-user", help="Create a user")
        @click.option(
            "--login",
            help="Login name of the new user",
            type=click.STRING,
            required=True,
            show_default=False,
        )
        @click.option(
            "--password",
            help="Password",
            type=click.STRING,
            required=True,
            show_default=False,
        )
        @click.option(
            "--superuser",
            help="Make it a superuser",
            type=click.BOOL,
            default=False,
            required=False,
            show_default=False,
            is_flag=True,
        )
        def create_user(login: str, password: str, superuser: bool = False) -> None:
            """Create a user."""
            click.echo("Running create user")
            _run_task(create_user_service(login=login, password=password, superuser=superuser))

        @cli.command(name="reset-password", help="Reset user password")
        @click.option(
            "--login",
            help="Login name of the user",
            type=click.STRING,
            required=True,
            show_default=False,
        )
        @click.option(
            "--password",
            help="New password",
            type=click.STRING,
            required=True,
            show_default=False,
        )
        def reset_password(login: str, password: str) -> None:
            """Create a user."""
            click.echo("Running reset-user")
            _run_task(reset_password_service(login=login, password=password))
