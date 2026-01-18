# Copyright (C) 2026 Stormy-RPG
# SPDX-License-Identifier: AGPL-3.0-only
import os
import datetime
import pkgutil

from typing import Iterator
from types import FrameType

import aiohttp


class Other:
    @staticmethod
    def get_total_lines_of_code() -> int:
        """
        Calculate total Python source lines in project.
        Returns total line count as integer.
        """
        # Directories to scan
        scan_dirs = ["./cogs", "./models", "./utils"]
        total_lines = 0
        
        for directory in scan_dirs:
            if os.path.exists(directory):
                for root, _, files in os.walk(directory):
                    total_lines += sum(
                        1 for file in files 
                        if file.endswith(".py")
                        for _ in open(os.path.join(root, file), encoding='utf-8')
                    )
        
        # Add main.py if exists
        if os.path.exists("./main.py"):
            with open("./main.py", "r", encoding="utf-8") as f:
                total_lines += sum(1 for _ in f)
        
        return total_lines
    

    @staticmethod
    async def get_last_update_time(github_token: str) -> int:
        """
        Retrieves the timestamp of the latest commit in the GitHub repository.

        This method performs an asynchronous HTTP request to the GitHub API
        to fetch the commit history. It extracts the date of the most recent
        commit and returns it as a Unix timestamp.

        Parameters
        ----------
        github_token : str
            GitHub personal access token for API authentication.

        Returns
        -------
        int | None
            Unix timestamp of the latest commit, or None on error.

        Notes
        -----
        - The method will return None if the API request fails (e.g., due to
          invalid token or repository inaccessibility).
        - An error message will be printed to console on failure.

        Examples
        --------
        >>> github_token = "your_github_token_here"
        >>> last_update = await Other.get_last_update_time(github_token)
        >>> print(last_update)
        1633036800  # Example Unix timestamp
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.github.com/repos/Stormy-RPG/Telegram-Mail-Bot/commits", 
                headers={"Authorization": f"token {github_token}"}
            ) as response:
                if response.status != 200:
                    print(f"Failed to fetch commits: HTTP {response.status}")
                    return None
                data = await response.json()
                timestamp = data[0]["commit"]["committer"]["date"]
                return int(datetime.datetime.fromisoformat(timestamp).timestamp())


    @staticmethod
    def get_caller_info(frame: FrameType) -> tuple[str, str, int, str]:
        """
        Extracts caller information from a given frame object.

        This method retrieves the filename, line number, and function name
        of the calling function by examining the provided frame's back frame.

        Parameters
        ----------
        frame : FrameType
            The current frame object from which to trace the caller.
            Typically obtained via `inspect.currentframe()`.

        Returns
        -------
        tuple[str, str, int, str]
            A 4-element tuple containing:
            - Absolute file path of the caller
            - Relative file path (from current working directory)
            - Line number in the source file
            - Name of the calling function

        Examples
        --------
        >>> import inspect
        >>> frame = inspect.currentframe()
        >>> info = Other.get_caller_info(frame)
        >>> print(info)
        ('/home/user/project/module.py', 'module.py', 42, 'main_function')
        
        Notes
        -----
        Useful for debugging, logging, and runtime introspection.
        Requires passing a valid frame object from the call stack.
        """
        caller_frame = frame.f_back
        caller_filename = caller_frame.f_code.co_filename
        caller_lineno = caller_frame.f_lineno
        caller_function_name = caller_frame.f_code.co_name

        return (
            caller_filename,
            os.path.relpath(caller_filename),
            caller_lineno,
            caller_function_name
        )


    @classmethod
    def search_directory(cls, path: str) -> Iterator[str]:
        """
        Recursively discovers Python modules in a directory and yields their
        importable names in dot notation.
        
        This method performs a safe, recursive traversal of the specified
        directory to find all Python modules (.py files) and packages.
        It returns module names formatted for direct use with importlib.
        
        Parameters
        ----------
        path : str
            Directory path to search for Python modules. Must be within the
            current working directory for security reasons.
        
        Yields
        ------
        str
            Importable module names in dot notation (e.g., "package.sub.module").
        
        Raises
        ------
        ValueError
            - If path contains ".." (parent directory access attempted)
            - If path doesn't exist
            - If path is not a directory
        
        Examples
        --------
        >>> for module in MyClass.search_directory("myapp"):
        ...     print(module)
        myapp.core
        myapp.utils.helpers
        myapp.plugins.validator
        
        Notes
        -----
        - Requires __init__.py files for package recognition
        - Uses pkgutil.iter_modules() for module discovery
        - Security: blocks access to parent directories (../)
        - Recursive: traverses all subdirectories
        """
        relpath = os.path.relpath(path)
        if ".." in relpath:
            raise ValueError("For modules outside cwd, package must be specified")

        abspath = os.path.abspath(path)
        if not os.path.exists(relpath):
            raise ValueError(f"The specified path \"{abspath}\" does not exist")
        if not os.path.isdir(relpath):
            raise ValueError(f"The specified path \"{abspath}\" is not a directory")

        prefix = relpath.replace(os.sep, ".")
        if prefix in ("", "."):
            prefix = ""
        else:
            prefix += "."

        for _, name, ispkg in pkgutil.iter_modules([path]):
            if ispkg:
                yield from cls.search_directory(os.path.join(path, name))
            else:
                yield prefix + name