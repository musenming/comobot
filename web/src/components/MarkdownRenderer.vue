<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js/lib/core'
import javascript from 'highlight.js/lib/languages/javascript'
import python from 'highlight.js/lib/languages/python'
import json from 'highlight.js/lib/languages/json'
import bash from 'highlight.js/lib/languages/bash'
import typescript from 'highlight.js/lib/languages/typescript'
import 'highlight.js/styles/github-dark.min.css'

hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('python', python)
hljs.registerLanguage('json', json)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('typescript', typescript)

const props = defineProps<{
  content: string
}>()

marked.setOptions({
  breaks: true,
  gfm: true,
})

const rendered = computed(() => {
  let html = marked(props.content || '') as string

  // Post-process code blocks for highlighting
  html = html.replace(
    /<pre><code class="language-(\w+)">([\s\S]*?)<\/code><\/pre>/g,
    (_, lang, code) => {
      try {
        const decoded = code
          .replace(/&amp;/g, '&')
          .replace(/&lt;/g, '<')
          .replace(/&gt;/g, '>')
          .replace(/&quot;/g, '"')
        const highlighted = hljs.highlight(decoded, { language: lang }).value
        return `<pre class="code-block"><div class="code-header"><span class="code-lang">${lang}</span><button class="code-copy" onclick="(function(btn){var t=btn.closest('pre').querySelector('code').textContent;if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t).catch(function(){var a=document.createElement('textarea');a.value=t;a.style.position='fixed';a.style.opacity='0';document.body.appendChild(a);a.select();document.execCommand('copy');document.body.removeChild(a)})}else{var a=document.createElement('textarea');a.value=t;a.style.position='fixed';a.style.opacity='0';document.body.appendChild(a);a.select();document.execCommand('copy');document.body.removeChild(a)}btn.textContent='Copied!';setTimeout(function(){btn.textContent='Copy'},1500)})(this)">Copy</button></div><code class="hljs language-${lang}">${highlighted}</code></pre>`
      } catch {
        return `<pre class="code-block"><code>${code}</code></pre>`
      }
    },
  )

  // Make links open in new tab
  html = html.replace(/<a /g, '<a target="_blank" rel="noopener" ')

  return html
})
</script>

<template>
  <div class="markdown-body" v-html="rendered" />
</template>

<style>
.markdown-body {
  font-size: var(--text-base);
  line-height: 1.6;
  color: var(--text-primary);
  word-break: break-word;
}
.markdown-body p {
  margin: 0 0 var(--space-3);
}
.markdown-body p:last-child {
  margin-bottom: 0;
}
.markdown-body a {
  color: var(--accent-blue);
  text-decoration: none;
}
.markdown-body a:hover {
  text-decoration: underline;
}
.markdown-body .code-block {
  background: var(--bg-muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow: hidden;
  margin: var(--space-3) 0;
}
.markdown-body .code-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-1) var(--space-3);
  background: var(--border);
  font-size: var(--text-xs);
}
.markdown-body .code-lang {
  color: var(--text-muted);
}
.markdown-body .code-copy {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: var(--text-xs);
  font-family: inherit;
}
.markdown-body .code-copy:hover {
  color: var(--text-primary);
}
.markdown-body code {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: var(--text-sm);
}
.markdown-body pre code {
  display: block;
  padding: var(--space-3);
  overflow-x: auto;
}
.markdown-body :not(pre) > code {
  background: var(--bg-muted);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-size: 0.9em;
}
.markdown-body table {
  border-collapse: collapse;
  width: 100%;
  margin: var(--space-3) 0;
  overflow-x: auto;
  display: block;
}
.markdown-body th,
.markdown-body td {
  border: 1px solid var(--border);
  padding: var(--space-2) var(--space-3);
  text-align: left;
  font-size: var(--text-sm);
}
.markdown-body th {
  background: var(--bg-muted);
  font-weight: 500;
}
.markdown-body blockquote {
  margin: var(--space-3) 0;
  padding: var(--space-2) var(--space-4);
  border-left: 3px solid var(--border);
  color: var(--text-secondary);
}
.markdown-body ul,
.markdown-body ol {
  padding-left: var(--space-6);
  margin: var(--space-2) 0;
}
.markdown-body img {
  max-width: 100%;
  height: auto;
  border-radius: var(--radius-md);
  margin: var(--space-2) 0;
  cursor: pointer;
}
</style>
