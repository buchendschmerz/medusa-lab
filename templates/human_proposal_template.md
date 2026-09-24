{#- ==========================================================================
    Medusa Lab — 【実験提案書】人間がやると面白い仮説＆実験プロトコル
    Rendered by medusa/agents/writer.py (Jinja2). Labels come from PROPOSAL_LABELS
    so the same template serves Japanese (default) and English labs.
    ========================================================================== -#}
# 【{{ t.doc }}】{{ idea.title }}

> 🐍 **{{ lab.name }}** · {{ t.cycle }} `{{ cycle_id }}` · {{ t.theme }}: 「{{ theme.title }}」<br>
> {{ t.authors }}: 🧠 Analyst（設計） · 📝 Writer（執筆） · 🖍️ Reviewer（査読） · {{ t.generated }}: {{ generated }}<br>
> **{{ t.status }}:** ⏳ {{ t.status_value }}

> [!NOTE]
> {{ t.disclaimer }}

## 0. {{ t.tldr }}

- **{{ t.hypothesis }}:** {{ idea.hypothesis }}
- **{{ t.design_type }}:** {{ design_label }} ／ **{{ t.power }}:** {{ t.per_condition }} n = {{ idea.sample_size }}
- **{{ t.fun }}:** {{ idea.fun_factor }}

## 1. {{ t.fun }}

{{ idea.fun_factor }}

## 2. {{ t.hypothesis }}

**{{ idea.hypothesis_id or idea.id }}** — {{ idea.hypothesis }}

## 3. {{ t.why_human }}

{{ idea.why_human }}

## 4. {{ t.design }}

| | |
|---|---|
| {{ t.design_type }} | {{ design_label | cell }} |
| {{ t.participants }} | {{ idea.participants | cell }} |
| {{ t.power }} | {{ t.per_condition }} **n = {{ idea.sample_size }}** {{ t.units }}（Cohen's d = {{ idea.effect_size_d }}, α = {{ idea.alpha }}, 1−β = {{ idea.power }}） |

### 4.1 {{ t.conditions }}

{% for c in idea.conditions %}
- {{ c }}
{% endfor %}

### 4.2 {{ t.procedure }}

{% for p in idea.procedure %}
{{ loop.index }}. {{ p }}
{% endfor %}

### 4.3 {{ t.measures }}

{% for m in idea.measures %}
- {{ m }}
{% endfor %}

### 4.4 {{ t.analysis }}

{{ idea.analysis_plan }}

## 5. {{ t.link }}

{{ idea.in_silico_link }}
{% if findings %}

**{{ t.sim_findings }}:**

{% for f in findings %}
- {{ f }}
{% endfor %}
{% endif %}

## 6. {{ t.ethics }}

{% for e in idea.ethics %}
- [ ] {{ e }}
{% endfor %}

## 7. {{ t.materials }}

{% for m in idea.materials %}
- {{ m }}
{% endfor %}

**{{ t.duration }}:** {{ idea.duration }} ／ **{{ t.cost }}:** {{ idea.cost_estimate }}

## 8. {{ t.risks }}

{% for r in idea.risks %}
- {{ r }}
{% endfor %}

## 9. {{ t.next }}

{% for a in t.actions %}
- [ ] {{ a }}
{% endfor %}

## 10. {{ t.review }}

{% if review %}
> **{{ review.reviewer }}** — `{{ review.decision }}`（{{ "%.1f" | format(review.mean_score) }}/5）<br>
> {{ review.summary }}

{% if review.strengths %}
**{{ t.strengths }}**

{% for x in review.strengths %}
- {{ x }}
{% endfor %}
{% endif %}
{% if review.weaknesses %}

**{{ t.weaknesses }}**

{% for x in review.weaknesses %}
- {{ x }}
{% endfor %}
{% endif %}
{% if review.requests %}

**{{ t.requests }}**

{% for x in review.requests %}
- [ ] {{ x }}
{% endfor %}
{% endif %}
{% else %}
{{ t.no_review }}
{% endif %}
{% if literature %}

## {{ t.literature }}

{% for it in literature %}
- {{ it.short_authors() }} ({{ it.year or "n.d." }}). *{{ it.title }}*. {{ it.venue }}{% if it.url %} <{{ it.url }}>{% endif %}

{% endfor %}
{% endif %}
