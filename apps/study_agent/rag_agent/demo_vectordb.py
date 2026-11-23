"""
VectorDB 수동 테스트 스크립트.
에이전트 없이 직접 파일을 추가하고 검색할 수 있다.

사용법:
    .venv/bin/python demo_vectordb.py
"""

import sys, os

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("EMBED_MODEL", "local")   # bge-m3 (로컬, 첫 실행 시 ~500MB 다운로드)
# os.environ["EMBED_MODEL"] = "openai"           # OpenAI 사용 시 주석 해제 + OPENAI_API_KEY 필요

from vector_db import VectorDBManager

db = VectorDBManager()


def cmd_add(path: str, title: str):
    """파일을 VectorDB에 추가"""
    if not os.path.exists(path):
        print(f"[ERROR] 파일 없음: {path}")
        return
    print(f"  추가 중: {path} → title='{title}'")
    result = db.add_document(file_path=path, title=title)
    print(f"  완료: {result['chunks_added']}개 chunk 저장됨")


def cmd_search(query: str, title: str, top_k: int = 5):
    """VectorDB에서 검색"""
    hits = db.search(query=query, title=title, top_k=top_k)
    if not hits:
        print(f"  결과 없음 (title='{title}'이 존재하지 않거나 비어있음)")
        return
    for i, h in enumerate(hits, 1):
        print(f"\n  [{i}] score={h['score']:.4f}  source={h['source']}  page={h['page']}")
        print(f"       {(h['parent_text'] or '')[:120].replace(chr(10), ' ')}...")


def cmd_list():
    """저장된 타이틀 목록"""
    titles = db.list_titles()
    if not titles:
        print("  (비어있음)")
    for t in titles:
        files = db.list_files(t)
        print(f"  title='{t}' — {len(files)}개 파일: {files}")


def cmd_delete_file(title: str, file_name: str):
    db.delete_file(title=title, file_name=file_name)
    print(f"  삭제 완료: title='{title}' / file='{file_name}'")


def cmd_delete_title(title: str):
    db.delete_title(title=title)
    print(f"  타이틀 전체 삭제 완료: '{title}'")


def interactive():
    print("=== VectorDB 수동 테스트 ===")
    print("명령어: add / search / list / delete_file / delete_title / quit\n")

    while True:
        try:
            cmd = input("명령 입력 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료")
            break

        if not cmd:
            continue

        parts = cmd.split()
        action = parts[0].lower()

        if action == "quit":
            break

        elif action == "add":
            # add <파일경로> <타이틀>
            if len(parts) < 3:
                print("  사용법: add <파일경로> <타이틀>")
                continue
            cmd_add(path=parts[1], title=" ".join(parts[2:]))

        elif action == "search":
            # search <타이틀> <질의>
            if len(parts) < 3:
                print("  사용법: search <타이틀> <질의>")
                continue
            title = parts[1]
            query = " ".join(parts[2:])
            print(f"  검색: '{query}' in title='{title}'")
            cmd_search(query=query, title=title)

        elif action == "list":
            cmd_list()

        elif action == "delete_file":
            # delete_file <타이틀> <파일명>
            if len(parts) < 3:
                print("  사용법: delete_file <타이틀> <파일명>")
                continue
            cmd_delete_file(title=parts[1], file_name=" ".join(parts[2:]))

        elif action == "delete_title":
            # delete_title <타이틀>
            if len(parts) < 2:
                print("  사용법: delete_title <타이틀>")
                continue
            cmd_delete_title(title=" ".join(parts[1:]))

        else:
            print(f"  알 수 없는 명령: {action}")

    print("종료")


if __name__ == "__main__":
    interactive()
