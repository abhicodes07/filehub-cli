import argparse
import asyncio
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from subprocess import CalledProcessError
from typing import Any
from urllib.parse import urlsplit

import aiofiles
import httpx
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
)

# terminal colors
RESET = "\033[0m"  # called to return to standard terminal text color
BRIGHT_RED = "\033[91m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
WHITE = "\033[97m"

# download dir
DOWNLOAD_DIR = Path("Filehub")

# limit download to only 4 cpus
DOWNLOAD_LIMIT = 4
CPU_WORKERS = os.cpu_count()

# flags
BRANCH = False
FLATTEN = False


class BranchNotFoundError(Exception):
    """Raised when the user specified branch does not exist."""

    def __init__(self, branch: str, repository: str) -> None:
        self.branch = branch
        self.repository = repository
        message = (
            f"'{self.branch}' Branch does not exist on '{self.repository}' repository."
        )

        super().__init__(message)


def get_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="A simple CLI program to download specific files from Github repositories."
    )

    parser.add_argument(
        "-b",
        "--branch",
        nargs="?",
        default=None,
        help="Specify repository branch.",
    )
    parser.add_argument(
        "-f",
        "--flatten",
        action="store_true",
        help="Flatten the directory structure.\nBy default, directory structure of the file is preserved according to it's path on the repository.",
    )
    parser.add_argument("url", type=str, help="Required Github repository URL.")
    parser.add_argument("-p", "--path", help="Download path of the file.")

    args = parser.parse_args()
    repo_url = urlsplit(args.url)

    if repo_url.scheme not in ("http", "https"):
        parser.error("URL must start with http:// or https://")

    if repo_url.netloc != "github.com":
        parser.error(f"{BRIGHT_RED}{args.url}{RESET} is not a valid Github URL!")

    if args.branch:
        global BRANCH
        BRANCH = True

    if args.flatten:
        global FLATTEN
        FLATTEN = True

    return args


def check_branch_status(owner: str, repo: str, branch: str) -> bool:
    # verify the existence of the branch if provided as an argument.
    branch_url = f"https://api.github.com/repos/{owner}/{repo}/branches/{branch}"

    res = httpx.get(branch_url)
    if res.status_code == 200:
        return True

    return False


def parse_repo_url(cmd_args: argparse.Namespace) -> dict[str, str]:
    info = {}

    url = urlsplit(cmd_args.url)
    segments = url.path.strip("/").split("/")
    # print(segments)

    info["owner"] = segments[0]
    info["repository"] = segments[1]
    info["branch"] = ""
    info["path"] = ""

    # if url already consists the branch or has `blob` in it
    # and user provides a different branch
    # as an argument then ignore the branch flag
    global BRANCH
    if "tree" in segments or "blob" in segments and BRANCH:
        BRANCH = False

    # if branch is provided as an argument
    if BRANCH:
        # verify the existence of user provided branch
        if not check_branch_status(info["owner"], info["repository"], cmd_args.branch):
            raise BranchNotFoundError(cmd_args.branch, info["repository"])

        info["branch"] = cmd_args.branch
    else:
        # find branch in url
        if len(segments) > 2:
            for i in range(1, len(segments)):
                branch_name = "/".join(segments[3:][:i])
                if check_branch_status(info["owner"], info["repository"], branch_name):
                    info["branch"] = branch_name
                    info["path"] = "/".join(segments[3:][i:])
                    break
    # print(info)
    return info


def check_api_request_limit() -> dict[str, Any]:
    response = httpx.get("https://api.github.com/rate_limit").json()
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


async def get_repository_content(
    owner: str, name: str, branch: str, path: str | None = None
) -> dict:
    print("Fetching repository contents...\n")

    # f"https://api.github.com/repos/{owner}/{name}/contents/{path}?ref='{branch}'",
    repo_urls = [
        f"https://api.github.com/repos/{owner}/{name}/contents/{path}?ref={branch}"
        if branch
        else f"https://api.github.com/repos/{owner}/{name}/contents/{path}",
    ]

    response = []
    files = {}

    async with httpx.AsyncClient() as client:
        for i, req in enumerate(repo_urls):
            # print(BRIGHT_GREEN + f"[{i + 1}]" + RESET + " Fetched URL: ", end="")
            # print(BRIGHT_YELLOW + req + RESET)
            #
            res = await client.get(req)
            res.raise_for_status()
            response.append(res.json())
            # print(f"{BRIGHT_GREEN} {response} {RESET}")

            if response:
                # loop over the list of responses
                for res in response:
                    # print(f"{BRIGHT_YELLOW} {res} {RESET}")
                    if type(res) is list:
                        for content in res:
                            # print(f"{BRIGHT_RED} {content} {RESET}")
                            # fetch files and directories
                            if content["type"] == "file":
                                if content["name"] not in files:
                                    files[content["name"]] = {}
                                # files[content["name"]]["url"] = content["url"]
                                files[content["name"]]["download_url"] = content[
                                    "download_url"
                                ]
                                file_path = "/".join(content["path"].split("/")[:-1])
                                files[content["name"]]["path"] = file_path
                                files[content["name"]]["size"] = content["size"]
                            else:
                                # if the content is dir then create a new requests
                                # to fetch files from it
                                repo_urls.append(content["url"])
                    else:
                        if res["name"] not in files:
                            files[res["name"]] = {}
                        # files[res["name"]]["url"] = res["url"]
                        files[res["name"]]["download_url"] = res["download_url"]
                        files[res["name"]]["size"] = res["size"]

                        # truncate the file name from path
                        file_path = "/".join(res["path"].split("/")[:-1])
                        files[res["name"]]["path"] = file_path

            response.clear()
        print()

    return files


def select_files(files: dict | None = None) -> dict | None:
    if not files:
        return

    if len(files) < 2:
        return files

    file_names = list(files.keys())
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
        raise

    selected_files = result.stdout.split("\n")[:-1]
    selected_file_urls = {}

    print(f"{BRIGHT_GREEN}[+]{RESET} SELECTED FILES:\n")

    for i, selected in enumerate(selected_files, start=1):
        print(f"\t{BRIGHT_GREEN}[{i}]{RESET} {selected}")
        if selected not in selected_file_urls:
            selected_file_urls[selected] = {}
        selected_file_urls[selected]["download_url"] = files[selected]["download_url"]
        selected_file_urls[selected]["size"] = files[selected]["size"]
        selected_file_urls[selected]["path"] = files[selected]["path"]
    print()

    return selected_file_urls


async def download_single_file(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    progress: Progress,
    file_name: str,
    download_url: str,
    path: str,
    size: int,
    index: int,
) -> Path:
    if FLATTEN:
        path = ""

    file_path = Path(DOWNLOAD_DIR / path)
    file_path.mkdir(parents=True, exist_ok=True)
    download_path = file_path / file_name

    if download_path.exists():
        print(f"{BRIGHT_YELLOW}{file_name}{RESET} already exists!\n")
    else:
        async with semaphore:
            # print(f"{BRIGHT_GREEN}[{index + 1}] Downloading {file_name} ...{RESET}")
            task = progress.add_task("", total=size, filename=file_name)
            ts = int(time.time())
            url = f"{download_url}?ts={ts}"

            # response = await client.get(url, timeout=10, follow_redirects=True)
            async with client.stream("GET", url, follow_redirects=True) as response:
                response.raise_for_status()

                async with aiofiles.open(download_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=512 * 1024):
                        if chunk:
                            await f.write(chunk)
                            progress.update(task, advance=len(chunk))

            # print(
            #     f"{BRIGHT_GREEN}[*]{RESET} Downloaded {BRIGHT_GREEN}{file_name}{RESET} and saved to {BRIGHT_YELLOW}{download_path}{RESET}"
            # )
            progress.update(task, visible=False)
            progress.console.print(
                f"[green]Downloaded[/green] {file_name} and saved to [italic][yellow]{download_path}[/yellow][/italic]"
            )

    return download_path


async def download_files(files: dict[str, dict] | None = None) -> list[Path] | None:
    if not files:
        return

    progress = Progress(
        TextColumn("[bold blue]Downloading {task.fields[filename]}"),
        SpinnerColumn("simpleDots"),
        BarColumn(),
        "{task.percentage:>.0f}%",
        DownloadColumn(),
    )

    # NOTE: LIMIT PROCESSES SPAWN LIMIT IN CPU IN CASE THERE ARE THOUSANDS OF REQUESTS
    dl_semaphore = asyncio.Semaphore(DOWNLOAD_LIMIT)
    with progress:
        async with httpx.AsyncClient() as client:
            async with asyncio.TaskGroup() as tg:
                tasks = [
                    tg.create_task(
                        download_single_file(
                            client,
                            dl_semaphore,
                            progress,
                            file,
                            files[file]["download_url"],
                            files[file]["path"],
                            files[file]["size"],
                            i,
                        )
                    )
                    for i, file in enumerate(files)
                ]
            file_paths = [task.result() for task in tasks]

    return file_paths


def timing(start, fetch, download, finish):
    fetch_time = fetch - start
    select_time = download - fetch
    download_time = finish - download
    total_time = finish - start

    print(
        f"\nFetched files in: {BRIGHT_RED}{fetch_time:.2f}{RESET} seconds. {(fetch_time / total_time) * 100:.2f}% of total time.",
    )
    print(
        f"Selected files in: {BRIGHT_RED}{select_time:.2f}{RESET} seconds. {(select_time / total_time) * 100:.2f}% of total time.",
    )
    print(
        f"Downloaded files in: {BRIGHT_RED}{download_time:.2f}{RESET} seconds. {(download_time / total_time) * 100:.2f}% of total time.",
    )
    print(
        f"Total execution time: {BRIGHT_RED}{total_time:.2f}{RESET} seconds. {(total_time / total_time) * 100:.2f}% of total time.",
    )


async def main() -> None:
    args = get_arguments()
    repo = parse_repo_url(args)

    api_status = check_api_request_limit()
    if api_status["used_all"]:
        print(BRIGHT_RED + "Github API rate limit reached!" + RESET)
        print(BRIGHT_RED + "Try again in: " + RESET, end="")
        print(BRIGHT_YELLOW + api_status["reset_time"] + RESET)
        return

    print(f"{BRIGHT_GREEN}[+]{RESET} Repository name: ", end="")
    print(BRIGHT_YELLOW + repo["repository"] + RESET)

    print(f"{BRIGHT_GREEN}[+]{RESET} Owner: ", end="")
    print(BRIGHT_YELLOW + repo["owner"] + RESET)

    if repo["branch"]:
        print(f"{BRIGHT_GREEN}[+]{RESET} Branch: ", end="")
        print(BRIGHT_YELLOW + repo["branch"] + RESET)

    if repo["path"]:
        print(f"{BRIGHT_GREEN}[+]{RESET} Path: ", end="")
        print(BRIGHT_YELLOW + repo["path"] + RESET)
    print()

    # # fetch repository content
    repo_content = await get_repository_content(
        repo["owner"], repo["repository"], repo["branch"], repo["path"]
    )

    # select files
    selected_files = select_files(repo_content)

    # download selected files
    global DOWNLOAD_DIR
    DOWNLOAD_DIR = Path(repo["repository"])
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    file_paths = await download_files(selected_files)

    api_status = check_api_request_limit()
    if not api_status["used_all"]:
        print(
            f"\n{BRIGHT_YELLOW}[!]{RESET} Github API Remaining Rates: {BRIGHT_YELLOW}{api_status['rate_remaining']}{RESET}"
        )
        print(
            f"{BRIGHT_YELLOW}[!]{RESET} Github API Used Rates: {BRIGHT_YELLOW}{api_status['rate_used']}{RESET}"
        )


if __name__ == "__main__":
    asyncio.run(main())
