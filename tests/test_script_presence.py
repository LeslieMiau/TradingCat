from pathlib import Path


def test_validate_all_script_exists_and_wires_steps():
    script = Path("/Users/miau/Documents/TradingCat/scripts/validate_all.sh")
    content = script.read_text(encoding="utf-8")

    assert script.exists()
    assert "./scripts/doctor.sh" in content
    assert "./scripts/validate_broker.sh" in content
    assert "./scripts/simulated_order_cycle.sh" in content
    assert "TRADINGCAT_INCLUDE_ORDER_CHECK=true" in content
    assert "TRADINGCAT_INCLUDE_EXECUTION_RUN=true" in content
    assert "TRADINGCAT_INCLUDE_MANUAL_RECONCILE=true" in content


def test_post_validate_script_exists_and_wires_reporting():
    script = Path("/Users/miau/Documents/TradingCat/scripts/post_validate.sh")
    content = script.read_text(encoding="utf-8")

    assert script.exists()
    assert "TRADINGCAT_ARCHIVE_REPORTS=true ./scripts/validate_all.sh" in content
    assert 'MODE="${2:-with-manual-cycle}"' in content
    assert "./scripts/latest_report.sh" in content
    assert "./scripts/report_markdown.sh latest" in content


def test_opend_check_script_exists_and_uses_socket_probe():
    script = Path("/Users/miau/Documents/TradingCat/scripts/opend_check.sh")
    content = script.read_text(encoding="utf-8")

    assert script.exists()
    assert "socket.create_connection" in content
    assert "TRADINGCAT_FUTU_HOST" in content
    assert "TRADINGCAT_FUTU_PORT" in content


def test_init_postgres_script_exists():
    script = Path("/Users/miau/Documents/TradingCat/scripts/init_postgres.sh")
    content = script.read_text(encoding="utf-8")

    assert script.exists()
    assert "createdb" in content
    assert "TRADINGCAT_POSTGRES_ENABLED=true" in content
