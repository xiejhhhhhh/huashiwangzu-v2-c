---
name: knowledge-search-sop
description: 知识库多跳检索标准步骤，先 search 再 get_block 最后实体消歧，确保答案准确
allowed-tools:
  - knowledge__search
  - knowledge__get_block
  - knowledge__get_entity_dictionary
effort: 3
enabled: true
---

## Knowledge Search Standard Operating Procedure

When the user asks a question that requires knowledge base retrieval, follow these steps in order:

### Step 1: Broad Search
Call `knowledge__search` with the user's question as the query. Use `top_k=5` for breadth. Review the returned chunks for relevance.

### Step 2: Targeted Block Retrieval
If the search results contain useful chunks, call `knowledge__get_block` with the `block_id` from the most relevant chunk to get the full block context.

### Step 3: Entity Disambiguation
If the results mention entities (brand names, product names, ingredient names), call `knowledge__get_entity_dictionary` with the entity name to get the authoritative definition.

### Step 4: Synthesize
Combine the results from all three steps into your answer. Always cite the source document name and page number at the end.

### When to skip steps
- If `search` returns 0 results, skip Step 2 and 3, tell the user "知识库中未找到相关信息"
- If the answer is clearly covered by a single chunk, skip Step 3
