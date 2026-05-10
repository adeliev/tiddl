from typer import Typer

from .url import url_subcommand
from .fav import fav_subcommand
from .search import search_subcommand
from .from_file import from_file_subcommand


SUBCOMMANDS: list[Typer] = [url_subcommand, fav_subcommand, search_subcommand, from_file_subcommand]


def register_subcommands(app: Typer):
    for sub_command in SUBCOMMANDS:
        app.add_typer(sub_command)
