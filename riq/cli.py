"""Command line helpers: `flask --app app demo`."""
from __future__ import annotations

from pathlib import Path

import click
from flask import Flask

from .auth import hash_password
from .demo import DEMO_JOB_DESCRIPTION, DEMO_JOB_TITLE, DEMO_SKILLS, DEMO_USERNAME, write_demo_files
from .extensions import db
from .models import User


def register_cli(app: Flask) -> None:
    @app.cli.command("demo")
    @click.option("--output", default="demo_resumes", show_default=True, help="Folder for the sample resumes.")
    @click.option("--password", default="Demo-Pass-123", show_default=True, help="Password for the demo account.")
    def demo(output: str, password: str) -> None:
        """Create a demo company account and sample resumes to upload."""
        if app.config["ENV_NAME"] == "production":
            raise click.ClickException("Refusing to create a demo account with a known password in production.")
        files = write_demo_files(Path(output))
        user = db.session.query(User).filter_by(username=DEMO_USERNAME).first()
        if user is None:
            user = User(username=DEMO_USERNAME, email="demo@resumeiq.example", company_name="Demo Company",
                        phone="+91 90000 00000", address="1 Demo Street, Hyderabad", industry="Software",
                        password_hash=hash_password(password))
            db.session.add(user)
            db.session.commit()
            click.echo(f"Created demo account '{DEMO_USERNAME}'.")
        else:
            user.password_hash = hash_password(password)
            user.pw_version += 1
            db.session.commit()
            click.echo(f"Demo account '{DEMO_USERNAME}' already existed; password reset.")
        click.echo(f"\nLogin:    username '{DEMO_USERNAME}'  password '{password}'")
        click.echo(f"Resumes:  {len(files)} files written to {Path(output).resolve()}")
        click.echo(f"Job:      '{DEMO_JOB_TITLE}'  skills: {', '.join(DEMO_SKILLS)}")
        click.echo(f"          description: {DEMO_JOB_DESCRIPTION[:60]}...")
        click.echo("\nSee DEMO.md for the walkthrough and the expected results.")
