---
name: 质量反馈（这章我读不下去）
about: 不用懂技术，告诉我们在哪一句掉了
title: "[quality] "
labels: quality
---

## 哪一章

- 书名 / 章号：
- 大概多少字：
- 用的是哪套文风（默认 plain-clean / 其他）：

## 在哪掉的（最重要）

贴**原句**（一到三句就够）：

> 

是哪种感觉（可多选，别的也可以写）：

- [ ] 像在解释，不像在发生
- [ ] 人物说话没有区别，分不清谁在说
- [ ] 场景是空的，不知道人在哪
- [ ] 情绪是告诉我的，不是让我感到的
- [ ] 结尾在总结/升华，不想看下一章

## 能不能把机器指标也贴上（可选但很有用）

```powershell
python -X utf8 -c "import sys;sys.path.insert(0,'tools');import review_panel as R;t=R.read(r'projects/<书名>/章节/<文件>.md');print(R.metrics(t))"
```

```text
# 贴输出
```

## 愿意被引用吗

- [ ] 可以（会在 CHANGELOG/README 里以「用户反馈」引用原句）
- [ ] 不要引用，只看数据
