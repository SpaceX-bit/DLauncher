"""Поддельный PySide6 для проверки ЛОГИКИ страниц без Qt (Qt в песочнице поставить нельзя).

Любой атрибут любого модуля PySide6.* — класс, который принимает любые аргументы и любые вызовы.
Ловит NameError/опечатки/неверные вызовы своих функций, но НЕ ловит неверное использование Qt API.

    import fakeqt; fakeqt.install()
    from dlauncher.ui.pages.play import PlayPage
"""
import sys
import types


class _Meta(type):
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return Any()

    def __or__(cls, other):
        return Any()

    def __ror__(cls, other):
        return Any()


class Any(metaclass=_Meta):
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        if name == "count":  # layout.count() -> 0, иначе while lay.count() зацикливается
            return lambda *a: 0
        return Any()

    def __call__(self, *a, **k):
        # декоратор вроде @Slot(object): вернуть саму функцию
        if len(a) == 1 and callable(a[0]) and not isinstance(a[0], Any) and not k:
            return a[0]
        return Any()

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0

    def __bool__(self):
        return True

    def __int__(self):
        return 0

    def __float__(self):
        return 0.0

    def __index__(self):
        return 0

    def __or__(self, o):
        return Any()

    __ror__ = __and__ = __rand__ = __add__ = __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = __or__
    __truediv__ = __rtruediv__ = __floordiv__ = __rfloordiv__ = __or__

    def __lt__(self, o):
        return False

    __le__ = __gt__ = __ge__ = __lt__

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeModule(types.ModuleType):
    def __init__(self, name):
        super().__init__(name)
        self._cache = {}

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        if name not in self._cache:
            self._cache[name] = type(name, (Any,), {})
        return self._cache[name]


def install():
    for n in ("PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets", "PySide6.QtNetwork",
              "PySide6.QtMultimedia", "PySide6.QtSvg"):
        if n not in sys.modules or not isinstance(sys.modules[n], _FakeModule):
            sys.modules[n] = _FakeModule(n)
