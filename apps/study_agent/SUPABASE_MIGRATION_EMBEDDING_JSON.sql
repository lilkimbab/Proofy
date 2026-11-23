alter table document_chunks
add column if not exists embedding_json jsonb;

comment on column document_chunks.embedding_json is
'Stores non-1536 dimensional embeddings such as Ollama embeddinggemma 768d. OpenAI 1536d can still use the pgvector embedding column.';
