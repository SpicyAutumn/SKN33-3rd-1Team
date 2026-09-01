"""
파이썬에서 바로 실행할 수 있는 런처입니다.

터미널: python run.py
PyCharm 등 IDE: 이 파일을 열고 Run 버튼(▶)을 누르면 됩니다.

내부적으로는 `streamlit run app/app.py`와 동일하게 동작합니다.
"""

import sys

from streamlit.web import cli as stcli

if __name__ == "__main__":
    sys.argv = ["streamlit", "run", "app/app.py"] + sys.argv[1:]
    sys.exit(stcli.main())
