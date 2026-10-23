import configparser

from mycat import app_config, main


def test_read_config_nonexistent(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "CFG_DIR", tmp_path)
    monkeypatch.setattr(app_config, "CFG_FILE", tmp_path / "config.ini")

    parser = app_config.read_config()
    assert isinstance(parser, configparser.ConfigParser)
    assert parser.sections() == []


def test_read_config_existing_utf8(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.ini"
    monkeypatch.setattr(app_config, "CFG_DIR", tmp_path)
    monkeypatch.setattr(app_config, "CFG_FILE", cfg_file)

    cfg_file.write_text("[settings]\ndefault_image = котик_🐱\n", encoding="utf-8")

    parser = app_config.read_config()
    assert parser.get("settings", "default_image") == "котик_🐱"


def test_read_config_corrupted(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.ini"
    monkeypatch.setattr(app_config, "CFG_DIR", tmp_path)
    monkeypatch.setattr(app_config, "CFG_FILE", cfg_file)

    cfg_file.write_text("invalid ini content without section header\n", encoding="utf-8")

    parser = app_config.read_config()
    assert parser.sections() == []


def test_load_config_default_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "CFG_DIR", tmp_path)
    monkeypatch.setattr(app_config, "CFG_FILE", tmp_path / "config.ini")

    pos = app_config.load_config(1920, 1080, 200, 200)
    assert pos["x"] == 1920 - 200 - app_config.DEFAULT_POSITION_OFFSET_X
    assert pos["y"] == 1080 - 200 - app_config.DEFAULT_POSITION_OFFSET_Y


def test_load_config_from_file(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.ini"
    monkeypatch.setattr(app_config, "CFG_DIR", tmp_path)
    monkeypatch.setattr(app_config, "CFG_FILE", cfg_file)

    cfg_file.write_text("[window]\nx = 42\ny = 84\n", encoding="utf-8")

    pos = app_config.load_config(1920, 1080, 200, 200)
    assert pos["x"] == 42
    assert pos["y"] == 84


def test_save_config(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.ini"
    monkeypatch.setattr(app_config, "CFG_DIR", tmp_path)
    monkeypatch.setattr(app_config, "CFG_FILE", cfg_file)

    app_config.save_config({"x": 100, "y": 200})
    parser = app_config.read_config()
    assert parser.get("window", "x") == "100"
    assert parser.get("window", "y") == "200"

    # Partial update: update x, y should remain
    app_config.save_config({"x": 150})
    parser = app_config.read_config()
    assert parser.get("window", "x") == "150"
    assert parser.get("window", "y") == "200"


def test_load_image_from_ini(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.ini"
    monkeypatch.setattr(app_config, "CFG_DIR", tmp_path)
    monkeypatch.setattr(app_config, "CFG_FILE", cfg_file)

    assert app_config.load_image_from_ini() is None

    cfg_file.write_text("[settings]\ndefault_image = sleepy_cat\n", encoding="utf-8")
    assert app_config.load_image_from_ini() == "sleepy_cat"


def test_save_image_to_ini(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.ini"
    monkeypatch.setattr(app_config, "CFG_DIR", tmp_path)
    monkeypatch.setattr(app_config, "CFG_FILE", cfg_file)

    app_config.save_image_to_ini("cat_wizard")
    assert app_config.load_image_from_ini() == "cat_wizard"

    # Second call with identical image should be a no-op
    app_config.save_image_to_ini("cat_wizard")
    assert app_config.load_image_from_ini() == "cat_wizard"


def test_load_wait_time_from_ini(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.ini"
    monkeypatch.setattr(app_config, "CFG_DIR", tmp_path)
    monkeypatch.setattr(app_config, "CFG_FILE", cfg_file)

    assert app_config.load_wait_time_from_ini(5.0) == 5.0

    cfg_file.write_text("[settings]\nwait_time = 15.5\n", encoding="utf-8")
    assert app_config.load_wait_time_from_ini(5.0) == 15.5

    cfg_file.write_text("[settings]\nwait_time = invalid\n", encoding="utf-8")
    assert app_config.load_wait_time_from_ini(5.0) == 5.0


def test_main_reexports():
    for name in [
        "read_config",
        "load_config",
        "save_config",
        "load_image_from_ini",
        "save_image_to_ini",
        "load_wait_time_from_ini",
        "secure_write_config",
        "CFG_DIR",
        "CFG_FILE",
    ]:
        assert getattr(main, name) is getattr(app_config, name)
