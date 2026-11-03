"""Undo any ledger entry.

  python -m loop.rollback last          undo the newest change not yet undone
  python -m loop.rollback <ledger id>   undo that one
  python -m loop.rollback --list        show what can be undone
In Actions: tick → Run workflow is for jobs; use the 'rollback' workflow with the ledger id.
"""
import sys

from . import clients
from .core import NamedStop, ledger, ledger_add, spath

UNPUBLISH = """mutation($id:ID!){ articleUpdate(id:$id, article:{isPublished:false}){ article{ id isPublished } userErrors{ field message } } }"""
REPUBLISH = """mutation($id:ID!){ articleUpdate(id:$id, article:{isPublished:true}){ article{ id isPublished } userErrors{ field message } } }"""
BODY = """mutation($id:ID!,$b:String!){ articleUpdate(id:$id, article:{body:$b}){ article{ id } userErrors{ field message } } }"""
DEL_REDIRECT = """mutation($id:ID!){ urlRedirectDelete(id:$id){ deletedUrlRedirectId userErrors{ field message } } }"""


def undoable():
    done = {e.get("ref") for e in ledger() if e["action"] == "undo"}
    return [e for e in ledger() if e["action"] != "undo" and e["id"] not in done]


def apply_undo(u, gql):
    op = u["op"]
    if op == "unpublish":
        clients.user_errors(gql(UNPUBLISH, {"id": u["article_id"]})["articleUpdate"])
    elif op == "republish":
        clients.user_errors(gql(REPUBLISH, {"id": u["article_id"]})["articleUpdate"])
    elif op == "restore_body":
        clients.user_errors(gql(BODY, {"id": u["article_id"], "b": open(spath(u["backup"])).read()})["articleUpdate"])
    elif op == "delete_redirect":
        clients.user_errors(gql(DEL_REDIRECT, {"id": u["redirect_id"]})["urlRedirectDelete"])
    elif op == "restore_description":
        from . import heal
        heal.write_description(u["target"], u["old"], gql)
    else:
        raise NamedStop("UNKNOWN_UNDO", f"no way to undo '{op}'", 1)


def rollback(ref, gql=None):
    gql = gql or clients.gql
    todo = undoable()
    if not todo:
        raise NamedStop("NOTHING_TO_UNDO", "the ledger has nothing left to undo", 2)
    e = todo[-1] if ref == "last" else next((x for x in todo if x["id"] == ref), None)
    if not e:
        raise NamedStop("NOT_IN_LEDGER", f"{ref} is not an undoable ledger entry", 1)
    apply_undo(e["undo"], gql)
    redo = {"unpublish": {"op": "republish", "article_id": e["undo"].get("article_id")}}.get(e["undo"]["op"], {"op": "none"})
    ledger_add({"action": "undo", "ref": e["id"], "slug": e.get("slug"), "summary": f"Undid: {e.get('summary', e['action'])}", "undo": redo})
    return f"undid {e['id']} ({e.get('summary', e['action'])})"


def main(argv):
    if not argv or argv[0] == "--list":
        for e in undoable():
            print(e["id"], e["action"], e.get("summary", ""))
        return 0
    try:
        print(rollback(argv[0]))
        return 0
    except NamedStop as s:
        print(s, file=sys.stderr)
        return s.exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
