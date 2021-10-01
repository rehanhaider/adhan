import getpass
import typer
import time

app = typer.Typer()


def salam():
    username = typer.style(getpass.getuser(), fg=typer.colors.GREEN, bold=True)
    typer.echo(f"Assalamualaikum {username}")


def validate_inputs(lat: float, long: float, method: str):
    validator = {}

    validator["lat"] = True if lat else False
    validator["long"] = True if long else False
    validator["method"] = True if method else False

    return validator


@app.command()
def update_adhan_times(lat: float = None, long: float = None, method: str = None):
    salam()

    if lat and long and method:
        print(lat)
        # TODO: Set the configuration accordingly
    else:
        input_validation = validate_inputs(lat, long, method)
        input_count = sum(1 for value in input_validation.values() if value == True)
        if input_count != 0:
            for key, value in input_validation.items():
                if value == False:
                    typer.echo(f"You didn't provide: --{key}")
        else:
            typer.echo("No updated values provided")
            typer.echo("Checking for existing configuration files")


if __name__ == "__main__":
    app()
