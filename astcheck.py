"""Простая проверка неопределённых имён (замена pyflakes): python tests/astcheck.py [файлы...]"""
import ast
import builtins
import glob
import sys


def names_defined(tree):
    d = set(dir(builtins)) | {"__file__", "__name__"}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            d.add(n.name)
            if not isinstance(n, ast.ClassDef):
                a = n.args
                for x in a.args + a.kwonlyargs + a.posonlyargs:
                    d.add(x.arg)
                if a.vararg:
                    d.add(a.vararg.arg)
                if a.kwarg:
                    d.add(a.kwarg.arg)
        elif isinstance(n, ast.Lambda):
            a = n.args
            for x in a.args + a.kwonlyargs + a.posonlyargs:
                d.add(x.arg)
            if a.vararg:
                d.add(a.vararg.arg)
            if a.kwarg:
                d.add(a.kwarg.arg)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names:
                d.add((al.asname or al.name).split(".")[0])
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            d.add(n.id)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            d.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            d.update(n.names)
        elif isinstance(n, ast.arg):
            d.add(n.arg)
    return d


def check(path):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src, path)
    d = names_defined(tree)
    bad = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in d:
            bad.append((n.lineno, n.id))
    return bad


def check_private_attrs(path):
    """self._имя, которого в классе нигде нет (ни def, ни присваивания): именно так пропала _offer_import.
    Проверяются только имена с подчёркиванием — у Qt таких методов нет, ложных срабатываний не бывает."""
    tree = ast.parse(open(path, encoding="utf-8").read(), path)
    bad = []
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        defined = set()
        for n in ast.walk(cls):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined.add(n.name)
            elif isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store):
                defined.add(n.attr)
            elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                defined.add(n.id)
        for n in ast.walk(cls):
            if (isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load) and isinstance(n.value, ast.Name)
                    and n.value.id == "self" and n.attr.startswith("_") and not n.attr.startswith("__")
                    and n.attr not in defined):
                bad.append((n.lineno, f"self.{n.attr} (класс {cls.name})"))
    return bad


if __name__ == "__main__":
    files = sys.argv[1:] or glob.glob("dlauncher/**/*.py", recursive=True) + ["main.py"]
    total = 0
    for f in sorted(files):
        for ln, name in check(f):
            print(f"{f}:{ln}: undefined name {name}")
            total += 1
        for ln, name in check_private_attrs(f):
            print(f"{f}:{ln}: нет такого атрибута {name}")
            total += 1
    print("astcheck:", "OK" if not total else f"{total} problem(s)")
    sys.exit(1 if total else 0)
