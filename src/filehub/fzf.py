import subprocess
from subprocess import CalledProcessError


def select_files(files: list[dict]) -> list[dict]:
    """selection menu using fzf"""
    if not files:
        return files

    if len(files) < 2:
        return files

    # get aall the file names
    file_names = [file["name"] for file in files]
    file_input = "\n".join(file_names)

    try:
        result = subprocess.run(
            [
                "fzf",
                "-m",
                "--border-label",
                "Select Files 📂",
                "--height",
                "~50%",
                "--layout",
                "reverse",
                "--border",
                "--padding",
                "1,2",
                "--header",
                "TAB: mark | ENTER: confirm",
                "--input-label",
                "Input",
                "--exit-0",
            ],
            capture_output=True,
            text=True,
            check=True,
            input=file_input,
        )
    except CalledProcessError:
        print("No file selected, Aborting!")

    selected_files = result.stdout.split("\n")[:-1]
    selected = []

    for file in files:
        if file["name"] in selected_files:
            selected.append(file)
    print()

    return selected
