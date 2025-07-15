
import os
import ast
import pathlib

def get_python_files(path):
    path_obj = pathlib.Path(path)
    return [str(file) for file in path_obj.rglob('*.py')]

def parse_file(file_path):
    with open(file_path, "r", encoding="utf-8") as source:
        try:
            return ast.parse(source.read(), filename=file_path)
        except (SyntaxError, UnicodeDecodeError):
            return None 
