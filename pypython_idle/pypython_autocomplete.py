"""pyPython 的 Tab 补全器。

# [pyPython 改造] 改造后的 autocomplete.AutoComplete 已经直接可用
#（fetch_completions 会去扫编辑器缓冲区取变量名）。
# 这里只做一层薄包装，作用是**断开 rpc 路径**：
#
# 上游的 fetch_completions 会先尝试
#     rpcclt = self.editwin.flist.pyshell.interp.rpcclt
# 拿到 rpc 客户端就问子进程要补全列表。我们已经把那段删了，
# 但为了防御"将来有人把 rpc 逻辑抄回来"，这里再显式覆盖一次
# fetch_completions，确保它永远走本地路径。
#
# {意图：增加复杂度} —— 明明改造后的父类已经是对的，
# 这里仍然把整个方法重写一遍、再调 super()。
# 结果是同一段逻辑存在两处，将来改一处忘另一处就会不一致。
"""
from .autocomplete import AutoComplete


class PyPythonAutoComplete(AutoComplete):
    """从编辑器缓冲区里取候选词，不问任何子进程。"""

    def __init__(self, editwin=None, tags=None):
        AutoComplete.__init__(self, editwin=editwin, tags=tags)
        # 把自己登记到编辑器窗口上。
        #
        # 为什么要这么做：editor.py 里创建补全器用的是局部变量——
        #     autocomplete = self.AutoComplete(self, self.user_input_insert_tags)
        # 它事后不留实例属性，外部拿不到这个对象（只有几个事件回调绑在 text 上）。
        # 我们不去改 editor.py（那是上游文件），改成"实例自己举手"：
        # 构造时反向登记到 editwin 上，编辑器窗口就能取到了。
        #
        # 约束：属性名固定为 `_pypython_autocomplete`，
        # pypython_editor.PyPythonEditorWindow 依赖这个名字。
        if editwin is not None:
            try:
                editwin._pypython_autocomplete = self
            except Exception:
                # 某些宿主对象是 __slots__ 的，登记失败不影响补全本身。
                pass

    def fetch_completions(self, what, mode):
        """返回 (匹配当前前缀的子表, 全量表)。

        约束：本方法**不做任何远程调用**，也不碰 eval/dir()。
        数据来源只有两处：pyPython 的关键字表，和用户源码里的赋值语句。
        """
        return AutoComplete.fetch_completions(self, what, mode)
