import asyncio, subprocess, sys
try:
    from nitrogen import require
except ImportError:
    print("sodium: Nitrogen is not installed. Please install it using 'pip install wwn'.")
    exit(1)
Project = require("helium").Project
Color = require("magnesium.color").Color
FilePath = require("magnesium.filepath").FilePath


SODIUM: Project = Project(__file__, ".") # type: ignore
SODIUM.Project = Project
SODIUM.Color = Color
SODIUM.FilePath = FilePath
SODIUM.VERSION = "26.1"
SODIUM.OPTION_PREFIX = "--sodium-"
SODIUM.KNOWN_OPTIONS = ["bg", "bg-task", "show-tokens", "no-exec"]
SODIUM.KNOWN_COMMANDS = ["help", "version", "credits", "copyright", "license", "open-license"]
SODIUM.THEME_COLOR = Color.yellow

def title() -> str:
    print(f"{SODIUM.THEME_COLOR}sodium:info: {Color.bold}v{SODIUM.VERSION}{Color.reset}")

def main() -> None:
    args: list[str] = []
    options: list[str] = []
    for arg in sys.argv[1:]:
        if arg.startswith(SODIUM.OPTION_PREFIX):
            option: str = arg.removeprefix(SODIUM.OPTION_PREFIX)
            if option not in SODIUM.KNOWN_OPTIONS:
                print(f"{SODIUM.THEME_COLOR}sodium:warning:{Color.reset} unknown option: {option}")
            else:
                options.append(option)
        else:
            args.append(arg)
    if len(args) == 1 and not options and args[0].startswith("--"):
        if args[0].removeprefix("--") not in SODIUM.KNOWN_COMMANDS:
            print(f"{SODIUM.THEME_COLOR}sodium:{Color.reset} unknown command: {args[0].removeprefix('--')}")
            exit(1)
        title()
        match args[0]:
            case "--help":
                print(f"{Color.underline}available commands:{Color.reset}")
                for command in SODIUM.KNOWN_COMMANDS:
                    print(f"--{command}")
            case "--version":
                pass
            case "--credits":
                print("Sodium (sodiumlang) by Wednesware at https://wednesware.org")
                print()
                print("Contact at team@wednesware.org")
            case "--copyright":
                print("Copyright © 2026 Wednesware. All rights reserved.")
                print("Licensed under the MIT license.")
                print("Read more with `na --license`")
            case "--license":
                    license_path: FilePath = FilePath(__file__) / ".." / "LICENSE.md" # type: ignore
                    if not license_path.exists():
                        print(f"{SODIUM.THEME_COLOR}sodium:{Color.reset} could not find the license file.")
                        exit(1)
                    print(license_path.read())
                    print(f"{SODIUM.THEME_COLOR}sodium:hint:{Color.reset} Run `na --open-license` to open the license file.")
            case "--open-license":
                license_path: FilePath = FilePath(__file__) / ".." / "LICENSE.md" # type: ignore
                if not license_path.exists():
                    print(f"{SODIUM.THEME_COLOR}sodium:{Color.reset} could not find the license file.")
                    exit(1)
                subprocess.Popen(["xdg-open", str(FilePath(__file__) / ".." / "LICENSE.md")])
        exit(0)
    if "bg" in options and not "bg-task" in options:
        subprocess.Popen([
            sys.executable,
            "-m", "sodium",
            *sys.argv[1:],
            "--sodium-bg-task"
        ])
    else:
        SODIUM.script.run(args, options)

if __name__ == "__main__":
    main()