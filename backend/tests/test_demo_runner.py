"""Legacy outcome-based demo tests — superseded by test_scripted_demo.py。"""
import pytest

pytestmark = pytest.mark.skip(reason="Demo 已改为 fully scripted；见 test_scripted_demo.py")
