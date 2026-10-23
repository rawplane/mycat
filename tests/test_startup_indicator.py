"""Tests for the app icon helper used for the taskbar entry."""

from mycat import main


def test_app_icon_not_null(qapp):
    icon = main.make_app_icon()
    assert not icon.isNull()
    assert not icon.pixmap(64, 64).isNull()


def test_main_function_no_bare_keyboard_interrupt_handler():
    """main() sets up a SIGINT handler via signal.signal, so a bare
    except KeyboardInterrupt around app.exec() is dead code."""
    import ast
    import inspect
    from mycat import main as main_mod

    # Get source of main() function only
    src = inspect.getsource(main_mod.main)
    tree = ast.parse(src)

    # Find try/except blocks that catch KeyboardInterrupt
    dead_handlers = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                if (
                    handler.type is not None
                    and isinstance(handler.type, ast.Name)
                    and handler.type.id == "KeyboardInterrupt"
                ):
                    dead_handlers.append(handler)

    assert not dead_handlers, (
        f"main() has {len(dead_handlers)} bare KeyboardInterrupt handler(s) — "
        "dead code: SIGINT is handled by signal.signal → app.quit()"
    )


def test_gif_delay_fallback_empty():
    from mycat.cat_image import parse_gif_frame_delays
    assert parse_gif_frame_delays(b"not-a-gif") == []

