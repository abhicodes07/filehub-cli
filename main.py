import asyncio
import enum
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
RESET = "\033[0m"  # called to return to standard terminal text color

BRIGHT_RED = "\033[91m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_BLUE = "\033[94m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_CYAN = "\033[96m"
WHITE = "\033[97m"

DOWNLOAD_DIR = Path("filehub_downloads")


def get_repository_url():
    repo_url = sys.argv[1:]
    return repo_url[0]


def check_api_request_limit():
    response = requests.get("https://api.github.com/rate_limit").json()
    rate_remaining = response["rate"]["remaining"]
    rate_used = response["rate"]["used"]
    reset_time = datetime.fromtimestamp(response["rate"]["reset"])
    used_all = False
    if rate_remaining == 0 or rate_used == 60:
        used_all = True
    return {
        "rate_remaining": rate_remaining,
        "rate_used": rate_used,
        "used_all": used_all,
        "reset_time": str(reset_time),
    }


def get_repository_content(url: str) -> dict:
    print("\nFetching repository contents...\n")
    repo_slugs = url.split("/")
    repo_owner = repo_slugs[3]
    repo_name = repo_slugs[4]
    repo_branch = repo_slugs[5:7]
    path = ""

    if len(repo_slugs) > 5:
        path = "/".join(repo_slugs[7:])

    print(f"{BRIGHT_GREEN}[+]{RESET} Repository name: ", end="")
    print(BRIGHT_YELLOW + repo_name + RESET)

    print(f"{BRIGHT_GREEN}[+]{RESET} Owner: ", end="")
    print(BRIGHT_YELLOW + repo_owner + RESET)

    print(f"{BRIGHT_GREEN}[+]{RESET} Branch: ", end="")
    print(BRIGHT_YELLOW + repo_branch[1] + RESET)

    print(f"{BRIGHT_GREEN}[+]{RESET} Path: ", end="")
    print(BRIGHT_YELLOW + path + RESET)

    repo_urls = [
        f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{path}",
    ]

    response = []

    files = {}
    for i, req in enumerate(repo_urls):
        print(BRIGHT_GREEN + f"[{i + 1}]" + RESET + " Fetched URL: ", end="")
        print(BRIGHT_YELLOW + req + RESET)

        response.append(requests.get(req).json())

        if response:
            for res in response:
                for content in res:
                    # fetch files and directories
                    if content["type"] == "file":
                        if content["name"] not in files:
                            files[content["name"]] = {}
                        files[content["name"]]["url"] = content["url"]
                        files[content["name"]]["download_url"] = content["download_url"]
                    else:
                        # if the content is dir then create a new requests
                        # to fetch files inside it
                        repo_urls.append(content["url"])
        response.clear()

    return files


def select_files(files: dict):
    if not files:
        return

    file_names = list(files.keys())
    input = "\n".join(file_names)

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
            input=input,
        )
    except ChildProcessError:
        print("No file selected, Aborting!")
        return

    selected_files = result.stdout.split("\n")
    return selected_files


def download_single_file(file_name: str, file_url: dict):
    return True


def download_files(files: dict):
    selected = select_files(files)

    # for i, file_name in enumerate(selected):
    #     if file_name in files:
    #         print(list(files.keys())[i])
    #         print(files[file_name]["download_url"])

    # with requests.Session() as session:

    image_paths = [
        download_single_file(list(files.keys())[i], files[file]["download_url"])
        if file in files
        else f"{file} Not Found"
        for i, file in enumerate(selected)
    ]

    print(image_paths)


def main():
    api_status = check_api_request_limit()
    if api_status["used_all"]:
        print(BRIGHT_RED + "Github API rate limit reached!" + RESET)
        print(BRIGHT_RED + "Try again in: " + RESET, end="")
        print(BRIGHT_YELLOW + api_status["reset_time"] + RESET)
        return

    start_time = time.perf_counter()

    repo = get_repository_url()
    repo_content = get_repository_content(repo)  # returns files
    download_files(repo_content)

    finish_time = time.perf_counter()

    total_time = finish_time - start_time
    print(
        f"\nTotal execution time: {total_time:.2f} seconds. ",
    )

    api_status = check_api_request_limit()
    if not api_status["used_all"]:
        print(
            f"\n{BRIGHT_YELLOW}[!]{RESET} Github API Remaining Rates: {BRIGHT_YELLOW}{api_status['rate_remaining']}{RESET}"
        )
        print(
            f"{BRIGHT_YELLOW}[!]{RESET} Github API Used Rates: {BRIGHT_YELLOW}{api_status['rate_used']}{RESET}"
        )


if __name__ == "__main__":
    main()
