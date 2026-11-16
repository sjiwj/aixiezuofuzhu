# 写手任务单装配器 · chapter-beat

> 由 `chapter_budget.py` 出预算，`prompt_render.py` 填本模板。
> **硬规则**：`style` 或 `requirement` 缺一 → 不渲染、不出任务单（fail-closed）。
> **硬规则**：`style_anchor_samples` 缺失 → 不渲染（锚点缺失不许派写手）。

---

【风格层】{{style}}

---

【要求层】{{requirement}}

---

【这一拍】

- 内容：{{beat_summary}}
- 预算字数：{{beat_words}}
- 强度目标：{{beat_intensity}}
- 必须发生：{{must_happen}}
- 不许发生：{{must_not_happen}}
- **字数硬上限：≤ {{beat_words}} 字**（允许 ±10%）。到上限就收，不许为凑数加景、加心理、加总结；超出即判超预算，必须压缩后重交。

---

【锚点】{{style_anchor_samples}}

> 以上三段正样本一字不改，只模仿句式与节奏，情节不得搬进正文。

---

【禁词】{{never}}

---

【本章在全书的位置】

{{chapter_position}}
