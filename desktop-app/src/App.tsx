import { useState } from 'react'
import type { FormEvent as FormEventType } from 'react'
import './App.css'

type Message = { role: 'user' | 'assistant'; text: string }
type ViewMode = 'chat' | 'translator'

const starter: Message[] = [{ role: 'assistant', text: 'Салом. Я рядом, чтобы говорить на русском, лезгинском или сразу на двух языках.' }]

function App() {
  const [view, setView] = useState<ViewMode>('chat')
  const [messages, setMessages] = useState<Message[]>(starter)
  const [draft, setDraft] = useState('')
  const [model, setModel] = useState('gadz-instruct-lzg · 3B')
  const [language, setLanguage] = useState('Русский')
  const [online, setOnline] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [speaking, setSpeaking] = useState<number | null>(null)

  // Translator state
  const [srcLang, setSrcLang] = useState('rus_Cyrl')
  const [tgtLang, setTgtLang] = useState('lez_Cyrl')
  const [srcText, setSrcText] = useState('')
  const [tgtText, setTgtText] = useState('')
  const [translating, setTranslating] = useState(false)
  const [translateError, setTranslateError] = useState('')

  const submit = (event: FormEventType) => {
    event.preventDefault()
    const text = draft.trim()
    if (!text || loading) return
    const nextMessages = [...messages, { role: 'user' as const, text }]
    setMessages(nextMessages)
    setDraft('')
    setError('')
    setLoading(true)
    fetch('http://127.0.0.1:8765/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, model, answer_lang: language === 'Русский' ? 'rus_Cyrl' : 'lez_Cyrl', online, history: nextMessages.slice(-6).map((item) => ({ role: item.role, content: item.text })) }) })
      .then(async (response) => { const payload = await response.json(); if (!response.ok) throw new Error(payload.error || 'Backend недоступен'); return payload })
      .then((payload) => setMessages((current) => [...current, { role: 'assistant', text: payload.answer }, ...(payload.sources ? [{ role: 'assistant' as const, text: `ИСТОЧНИКИ\n${payload.sources}` }] : [])]))
      .catch((requestError: Error) => setError(`${requestError.message}. Запусти: python translate.py --server`))
      .finally(() => setLoading(false))
  }

  const clearChat = () => { if (!loading) { setMessages([]); setDraft(''); setError('') } }

  const speak = async (text: string, index: number) => {
    if (speaking !== null || text.startsWith('ИСТОЧНИКИ')) return
    setSpeaking(index)
    try {
      const response = await fetch('http://127.0.0.1:8765/api/speak', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, language: language === 'Русский' ? 'rus' : 'lez_Cyrl' }) })
      if (!response.ok) throw new Error('Не удалось озвучить ответ')
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : 'Ошибка озвучки') } finally { setSpeaking(null) }
  }

  const doTranslate = async () => {
    const text = srcText.trim()
    if (!text || translating) return
    setTranslating(true)
    setTranslateError('')
    setTgtText('')
    try {
      const response = await fetch('http://127.0.0.1:8765/api/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, src: srcLang, tgt: tgtLang }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || 'Ошибка перевода')
      setTgtText(data.translation)
    } catch (err) {
      setTranslateError(err instanceof Error ? err.message : 'Ошибка')
    } finally {
      setTranslating(false)
    }
  }

  const swapLanguages = () => {
    setSrcLang(tgtLang)
    setTgtLang(srcLang)
    setSrcText(tgtText)
    setTgtText(srcText)
  }

  const langName = (code: string) => code === 'rus_Cyrl' ? 'Русский' : 'Лезгинский'

  return <div className="app-shell">
    <div className="ambient-grid" aria-hidden="true" /><aside className="rail">
      <div className="logo"><span>g</span><div><b>gadz</b><small>LANGUAGE LAB</small></div></div>
      <button className="rail-action" onClick={clearChat}><span>+</span><em>Новый диалог</em></button>
      <div className="rail-section"><label>СЕЙЧАС</label><button className={`thread ${view === 'chat' ? 'active' : ''}`} onClick={() => setView('chat')}><i /> Лезгинский чат</button></div>
      <div className="rail-section"><label>ИНСТРУМЕНТЫ</label><button className={`thread ${view === 'translator' ? 'active' : ''}`} onClick={() => setView('translator')}><i /> ↗ Переводчик</button><span className="thread"><i /> ◌ Озвучка</span></div>
      <div className="rail-footer"><div className="online-mark"><i /> OFFLINE FIRST</div><div className="profile"><strong>G</strong><span>Локальный профиль</span><b>···</b></div></div>
    </aside>
    <main className="workspace">
      {view === 'chat' ? (
        <>
          <header className="topbar"><div className="crumb"><span>LAB / 01</span><h1>Лезгинский собеседник</h1></div><div className="controls"><label><small>МОДЕЛЬ</small><select value={model} onChange={(event) => setModel(event.target.value)}><option>gadz-instruct-lzg · 3B</option><option>gadz1-8b · 8B</option></select></label><label><small>ОТВЕТ</small><select value={language} onChange={(event) => setLanguage(event.target.value)}><option>Русский</option><option>Лезгинский</option></select></label><label className="web-switch"><input type="checkbox" checked={online} onChange={(event) => setOnline(event.target.checked)} /><span /> WEB</label></div></header>
          <section className="chat-stage">
            {messages.length === 0 && <div className="welcome"><div className="signal"><span /><span /><span /></div><div className="eyebrow">ГОВОРИ КАК ЕСТЬ</div><h2>Что у тебя на уме?</h2><p>Русский, лезгинский, смешанная речь. Один разговор, без облака.</p><div className="quick-prompts"><button onClick={() => setDraft('Переведи эту фразу на русский')}>Перевод</button><button onClick={() => setDraft('Объясни простыми словами')}>Объяснение</button><button onClick={() => setDraft('Поговори со мной на лезгинском')}>Диалог</button></div></div>}
            {messages.map((message, index) => <article className={`message ${message.role}`} key={`${message.role}-${index}`}><div className="message-index">{String(index + 1).padStart(2, '0')}</div><div className="message-content"><div className="message-head"><span className="role-dot" /> <b>{message.role === 'assistant' ? 'GADZ' : 'YOU'}</b><time>{message.role === 'assistant' ? 'ответ' : 'сообщение'}</time>{message.role === 'assistant' && !message.text.startsWith('ИСТОЧНИКИ') && <button className="speak-button" onClick={() => speak(message.text, index)} aria-label="Озвучить ответ">{speaking === index ? '◌' : '♪'}</button>}</div><p>{message.text}</p></div></article>)}
            {loading && <div className="generating"><span className="loader-line" /><b>ФОРМИРУЮ ОТВЕТ</b><small>локальный inference</small></div>}
            {error && <div className="error-box"><b>CONNECTION ISSUE</b><span>{error}</span></div>}
          </section>
          <div className="composer-zone"><form className="composer" onSubmit={submit}><div className="composer-top"><span className="compose-label">MESSAGE / {language.toUpperCase()}</span><span className="counter">{draft.length}/2000</span></div><textarea value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit(event) } }} placeholder="Напиши сообщение или задай вопрос..." rows={2} /><div className="composer-bottom"><span>SHIFT + ENTER — новая строка</span><button type="submit" disabled={!draft.trim() || loading}>SEND <b>↗</b></button></div></form><p className="footnote">Текст остается на этом устройстве, если WEB выключен.</p></div>
        </>
      ) : (
        <>
          <header className="topbar"><div className="crumb"><span>LAB / 02</span><h1>Переводчик</h1></div></header>
          <section className="chat-stage translator-stage">
            <div className="translator-container">
              <div className="translator-header">
                <h2 className="translator-title">Русский ⇄ Лезгинский</h2>
                <p className="translator-desc">Нейросетевой перевод. Текст не покидает ваш компьютер.</p>
              </div>
              <div className="translator-grid">
                <div className="translator-panel">
                  <div className="translator-panel-head">
                    <span className="translator-lang">{langName(srcLang)}</span>
                    <span className="translator-code">{srcLang}</span>
                  </div>
                  <textarea
                    className="translator-input"
                    value={srcText}
                    onChange={(e) => setSrcText(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doTranslate() } }}
                    placeholder="Введите текст для перевода..."
                    maxLength={2000}
                    rows={6}
                  />
                  <div className="translator-panel-foot">
                    <span>{srcText.length} / 2000</span>
                  </div>
                </div>
                <div className="translator-swap">
                  <button className="swap-circle" onClick={swapLanguages} title="Поменять языки">⇄</button>
                </div>
                <div className="translator-panel">
                  <div className="translator-panel-head">
                    <span className="translator-lang">{langName(tgtLang)}</span>
                    <span className="translator-code">{tgtLang}</span>
                  </div>
                  <textarea
                    className="translator-input translator-output"
                    value={tgtText}
                    readOnly
                    placeholder="Перевод появится здесь..."
                    rows={6}
                  />
                  <div className="translator-panel-foot">
                    <span>{tgtText.length} символов</span>
                    {tgtText && <button className="copy-btn" onClick={() => { navigator.clipboard.writeText(tgtText); }}>Копировать</button>}
                  </div>
                </div>
              </div>
              <div className="translator-actions">
                <button className="tr-btn tr-btn-primary" onClick={doTranslate} disabled={!srcText.trim() || translating}>
                  {translating ? 'Перевожу...' : 'Перевести'}
                </button>
                <button className="tr-btn tr-btn-secondary" onClick={() => { setSrcText(''); setTgtText(''); setTranslateError('') }}>Очистить</button>
              </div>
              {translateError && <div className="error-box"><b>ОШИБКА</b><span>{translateError}. Запусти: python translate.py --server</span></div>}
            </div>
          </section>
        </>
      )}
    </main>
  </div>
}

export default App
