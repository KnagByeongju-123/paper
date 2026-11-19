"""LibreOffice 로 Word 파일을 열어 목차(쪽번호)를 채우고 다시 저장, PDF 로도 내보낸다.

실행:  python scripts/finalize_lo.py output/thesis.docx [--pdf]
(build.py 가 자동으로 부르므로 직접 실행할 일은 거의 없다.)
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import uno  # LibreOffice 에 들어있는 파이썬 연결 모듈
from com.sun.star.beans import PropertyValue


def prop(name, value):
    p = PropertyValue()
    p.Name, p.Value = name, value
    return p


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    docx = Path(sys.argv[1]).resolve()
    want_pdf = "--pdf" in sys.argv
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    port = free_port()
    profile = Path(tempfile.mkdtemp(prefix="lo_profile_"))
    proc = subprocess.Popen(
        [soffice, "--headless", "--invisible", "--norestore", "--nologo",
         f"-env:UserInstallation={profile.as_uri()}",
         f"--accept=socket,host=127.0.0.1,port={port};urp;"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        local = uno.getComponentContext()
        resolver = local.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", local)
        ctx = None
        for _ in range(60):  # LibreOffice 가 뜰 때까지 최대 30초 대기
            try:
                ctx = resolver.resolve(
                    f"uno:socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext")
                break
            except Exception:
                time.sleep(0.5)
        if ctx is None:
            print("❌ LibreOffice 에 연결하지 못했습니다.")
            sys.exit(1)
        desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        doc = desktop.loadComponentFromURL(docx.as_uri(), "_blank", 0, (prop("Hidden", True),))

        # 목차/그림목차/표목차 갱신 (쪽이 밀릴 수 있어 두 번)
        for _ in range(2):
            indexes = doc.getDocumentIndexes()
            for i in range(indexes.getCount()):
                indexes.getByIndex(i).update()
            doc.refresh()

        doc.storeToURL(docx.as_uri(), (prop("FilterName", "MS Word 2007 XML"),))
        if want_pdf:
            doc.storeToURL(docx.with_suffix(".pdf").as_uri(),
                           (prop("FilterName", "writer_pdf_Export"),))
        doc.close(True)
        try:
            desktop.terminate()
        except Exception:
            pass
    finally:
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    main()
