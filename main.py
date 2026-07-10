import argparse
import asyncio
import os
import sys
import subprocess
import time
from datetime import datetime
from pathlib import Path
from subprocess import CalledProcessError
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
RATE_LIMIT = False


class BranchNotFoundError(Exception):
    """Raised when the user specified branch does not exist."""

    def __init__(self, branch: str, repository: str) -> None:
        self.branch = branch
        self.repository = repository
        message = (
            f"'{self.branch}' Branch does not exist on '{self.repository}' repository."
        )

        super().__init__(message)


class GithubRateLimitError(Exception):
    """Raised when the Github API rate limit is exceeded."""

    def __init__(self, used: int, reset_time: str) -> None:
        self.reset_time = reset_time
        self.used = used
        message = f"You have exhausted the Github API rate limit.\nUsed: {BRIGHT_YELLOW}{used}{RESET}\nTry again in {BRIGHT_YELLOW}{self.reset_time}{RESET}"
        super().__init__(message)


def get_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="A simple CLI program to download specific files from Github repositories."
    )

    # positional argument
    parser.add_argument(
        "url",
        type=str,
        metavar="URL",
        help="Required Github repository URL to download from.",
    )

    # optional arguments
    parser.add_argument("-p", "--path", help="Download path of the file.")
    parser.add_argument(
        "-b",
        "--branch",
        nargs="?",
        default=None,
        metavar="BRANCH",
        help="Branch of the repository to download from.",
    )
    parser.add_argument(
        "-f",
        "--flatten",
        action="store_true",
        help="Flatten directory structure.",
    )
    parser.add_argument(
        "-z",
        "--zip",
        action="store_true",
        help="Download zip archive of a repository.",
    )
    parser.add_argument(
        "-r",
        "--rate-limit",
        action="store_true",
        help="Check Github API rate limit uses.",
    )
    parser.add_argument(
        "-t", "--timing", action="store_true", help="Display run-time of the program."
    )
    parser.add_argument(
        "-d", "--dir", action="store_true", help="Download complete directory."
    )

    args = parser.parse_args()

    if args.branch:
        global BRANCH
        BRANCH = True

    if args.flatten:
        global FLATTEN
        FLATTEN = args.flatten

    if args.rate_limit:
        global RATE_LIMIT
        RATE_LIMIT = args.rate_limit

    return args


def validate_url(url: str):
    segments = urlsplit(url)

    if segments.netloc not in ("github.com", "gist.github.com"):
        raise ValueError(f"{url} is not a valid Github URL!")

    if segments.scheme not in ("https", "http"):
        raise ValueError("URL must start with http:// or https://")


def validate_branch(owner: str, repo: str, branch: str) -> bool:
    # verify the existence of the branch if provided as an argument.
    branch_url = f"https://api.github.com/repos/{owner}/{repo}/branches/{branch}"

    res = httpx.get(branch_url)
    if res.status_code != 200:
        return False

    return True


def parse_repo_url(cmd_args: argparse.Namespace) -> dict[str, str]:
    info = {}

    validate_url(cmd_args.url)

    url = urlsplit(cmd_args.url)
    path_segments = url.path.strip("/").split("/")

    if len(path_segments) < 2:
        match url.netloc:
            case "github.com":
                raise ValueError(
                    "Invalid URL: https://github.com/owner/repository is expected."
                )
            case "gist.github.com":
                raise ValueError(
                    "Invalid URL: https://gist.github.com/owner/gistid is expected."
                )

    info["owner"] = path_segments[0]
    info["repository"] = path_segments[1]
    info["branch"] = ""
    info["path"] = ""

    # if url already consists the branch or has `blob` in it
    # and user provides a different branch
    # as an argument then ignore the branch flag
    global BRANCH
    if "tree" in path_segments or "blob" in path_segments and BRANCH:
        BRANCH = False

    # if branch is provided as an argument
    if BRANCH:
        # verify the existence of user provided branch
        if not validate_branch(info["owner"], info["repository"], cmd_args.branch):
            raise BranchNotFoundError(cmd_args.branch, info["repository"])

        info["branch"] = cmd_args.branch
    else:
        # find branch in url
        if len(path_segments) > 2:
            if "blob" not in path_segments or "tree" not in path_segments:
                # NOTE: IN SOME CASES BRANCH NAME MAY LOOK LIKE PATH SUCH AS feat/something
                # SO TO IDENTIFY RIGHT BRANCH, CONSTRUCT AND VALIDATE BRANCH BY ITERATING
                # OVER PATH
                for i in range(1, len(path_segments)):
                    branch_name = "/".join(path_segments[3:][:i])
                    if validate_branch(info["owner"], info["repository"], branch_name):
                        info["branch"] = branch_name
                        # rest of the path after branch
                        info["path"] = "/".join(path_segments[3:][i:])
                        break
            else:
                raise ValueError(f"Invalid URL: {cmd_args.url} is not a valid URL.")
    # print(info)
    return info


def check_user_rate_limit() -> None:
    response = httpx.get("https://api.github.com/rate_limit").json()
    rate_remaining = response["rate"]["remaining"]
    rate_used = response["rate"]["used"]
    reset_time = datetime.fromtimestamp(response["rate"]["reset"])

    print(
        f"\n{BRIGHT_YELLOW}[!]{RESET} Github API Remaining Rates: {BRIGHT_YELLOW}{rate_remaining}{RESET}"
    )
    print(
        f"{BRIGHT_YELLOW}[!]{RESET} Github API Used Rates: {BRIGHT_YELLOW}{rate_used}{RESET}"
    )
    print(f"{BRIGHT_YELLOW}[!]{RESET} Reset: {BRIGHT_YELLOW}{str(reset_time)}{RESET}")


def check_api_rate_limit(headers: httpx.Headers) -> None:
    rate_limit_remaining = int(headers["x-ratelimit-remaining"])
    rate_limit_used = int(headers["x-ratelimit-used"])
    rate_limit_reset = int(headers["x-ratelimit-reset"])
    reset_time = str(datetime.fromtimestamp(rate_limit_reset))

    if rate_limit_remaining == 0 or rate_limit_used == 60:
        raise GithubRateLimitError(rate_limit_used, reset_time)


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

            res = await client.get(req)
            res.raise_for_status()

            headers = res.headers
            check_api_rate_limit(headers)

            response.append(res.json())
            # print(f"{BRIGHT_GREEN} {response} {RESET}")

            if response:
                # loop over the list of responses
                for res in response:
                    # print(f"{BRIGHT_YELLOW} {res} {RESET}")
                    if isinstance(res, list):
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
        "[ {task.percentage:>3.1f}% ]",
        " | ",
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
    files = await get_repository_content(
        repo["owner"], repo["repository"], repo["branch"], repo["path"]
    )

    # select files
    selected_files = select_files(files)

    # download selected files
    global DOWNLOAD_DIR
    DOWNLOAD_DIR = Path(repo["repository"])
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    file_paths = await download_files(selected_files)

    if RATE_LIMIT:
        check_user_rate_limit()


if __name__ == "__main__":
    asyncio.run(main())
