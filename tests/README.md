# 回归测试

## 怎么跑

在项目根目录：

```
python tests/run_all.py
```

退出码 0 = 全部通过。也可以单独跑某一个：

```
python tests/test_v2_core.py
```

## 有哪些

| 脚本 | 测什么 | 当前 |
|---|---|---|
| `run_all.py` | 总入口，逐个跑下面这些 | — |
| `test_adr0001_no_exec.py` | ADR-0001 硬约束：`exec`/`eval` 只能在 `main()` 基线段 | 通过 |
| `test_v2_core.py` | 第二版核心：while / for / def / return / class / self / 全局 / 递归 | 33/33 |
| `test_v2_errors.py` | 错误路径：递归深度、循环上限、参数个数、类型错误、语法错误 | 29/29 |
| `test_blank_lines.py` | 空行不吞 DEDENT（#23 的守卫） | 16/16 |
| `test_keyword_sync.py` | 6 份关键字表**真正 import 进来**做集合比较 | 全绿 |
| `test_examples.py` | `examples/hello.pypy` 整份能跑且输出符合预期 | 全绿 |
| `test_auto_indent.py` | 真实编辑器里按回车，6 个块关键字是否自动缩进 | 9/9 |
| `test_ide_v2.py` | IDE：高亮 / 补全 / 语法卡片 / F5 端到端 | 32/32 |

## 为什么测这些

### `test_keyword_sync.py` 为什么必须存在

关键字表在本项目有 **8 处副本**（见 `docs/decisions/0007`）。
漏改任何一处**都不会报错**，只会静默失效——比如新关键字不高亮、
不自动缩进、补全里没有。

所以这个脚本把**每一份都 import 进来**做集合比较。
**不要退化成文本匹配**：文本匹配查不出"名字对了但内容没改"。

### `test_blank_lines.py` 为什么必须存在

#23 是个非常隐蔽的 lexer bug：`_measure_indent()` 吃掉空行的换行符，
导致空行**下一行**的整段缩进比较被跳过，`DEDENT` 一个都不产出。
症状是"删掉空行程序就正常"。

这个 bug 在第一版（只有 `if`/`else`）时几乎走不到，
加了 `def`/`class` 之后"顶层语句之间空一行"成了最常见的排版，
立刻暴露。这个脚本就是防止它回来。

### `test_auto_indent.py` 为什么走真实编辑器

`pyparse.is_block_opener()` 的 `lo` 参数语义是
"取 `lo` 位置**之前**那条完整语句"。直接喂 offset 极容易喂错——
我连续试了三种摆法都返回 `False`（连 `if` 都是），一度以为是产品坏了。

改走**真实编辑器按回车**之后立刻验证通过。
**当一个 API 反复测不出预期时，先怀疑自己的调用姿势。**

## 写测试时踩过的坑

1. **构造器名少写一个下划线**：`def __init()` 写成 `def __init()`（少一个 `_`），
   于是构造器不存在，测试报"类没有定义 `__init__`"——**产品是对的，测试错了**。
2. **空输出被当成"必须有输出"**：`run()` 里 `all(...) if expect else bool(out)`
   把 `expect=[]` 当成"必须有输出"，两个正确行为被判失败。
   现在 `expect=None` 表示"不该有任何输出"。
3. **`is_block_opener()` 喂错 offset**（见上）。

**结论：报告失败之前，先确认测试测的是不是你以为的那件事。**
