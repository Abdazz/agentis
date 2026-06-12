'use client'

import { useState, useRef, useEffect } from 'react'
import { useTranslations } from 'next-intl'
import { useRouter } from '@/i18n/navigation'
import { apiFetch } from '@/lib/api'
import { Button } from './ui/button'
import { Textarea } from './ui/textarea'
import { TemplateModal } from './templates/TemplateModal'
import { Mic, Square, Loader2 } from 'lucide-react'

const MAX_FILE_SIZE = 50 * 1024 * 1024 // 50 MB
const MAX_FILES = 5
const ALLOWED_TYPES = [
  'application/pdf', 'text/plain', 'text/markdown',
  'application/json', 'text/csv',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
]

export function TaskForm() {
  const t = useTranslations('home')
  const router = useRouter()
  const [goal, setGoal] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [fileError, setFileError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [micState, setMicState] = useState<'idle' | 'recording' | 'processing'>('idle')
  const [micError, setMicError] = useState<string | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])

  const hasMicSupport = typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia

  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop()
      }
      mediaRecorderRef.current = null
    }
  }, [])

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    setFileError(null)
    const selected = Array.from(e.target.files ?? [])
    if (selected.length > MAX_FILES) {
      setFileError(`Maximum ${MAX_FILES} files allowed.`)
      return
    }
    for (const f of selected) {
      if (f.size > MAX_FILE_SIZE) {
        setFileError(`File "${f.name}" exceeds the 50 MB limit.`)
        return
      }
      if (!ALLOWED_TYPES.includes(f.type)) {
        setFileError(`File type "${f.type}" is not allowed.`)
        return
      }
    }
    setFiles(selected)
  }

  async function startRecording() {
    setMicError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      audioChunksRef.current = []
      const mimeType = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4'
      const mediaRecorder = new MediaRecorder(stream, { mimeType })
      mediaRecorderRef.current = mediaRecorder

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunksRef.current.push(e.data)
        }
      }

      mediaRecorder.onstop = async () => {
        // Stop all tracks to release the microphone
        stream.getTracks().forEach((track) => track.stop())

        const blob = new Blob(audioChunksRef.current, { type: mimeType })
        const fd = new FormData()
        fd.append('audio', blob, mimeType === 'audio/webm' ? 'recording.webm' : 'recording.mp4')
        setMicState('processing')
        try {
          const r = await apiFetch('/api/v1/voice/transcribe', { method: 'POST', body: fd })
          if (r.ok) {
            const data = await r.json() as { text: string; language: string; duration_seconds: number }
            setGoal(data.text)
          } else {
            const body = await r.json().catch(() => ({})) as { detail?: string }
            setMicError(body.detail ?? t('micError'))
          }
        } catch {
          setMicError(t('micError'))
        } finally {
          setMicState('idle')
        }
      }

      mediaRecorder.start()
      setMicState('recording')
    } catch {
      setMicError(t('micError'))
      setMicState('idle')
    }
  }

  function stopRecording() {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    mediaRecorderRef.current = null
  }

  function handleMicClick() {
    if (micState === 'idle') {
      void startRecording()
    } else if (micState === 'recording') {
      stopRecording()
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!goal.trim()) return
    setIsSubmitting(true)
    try {
      let body: BodyInit
      let headers: Record<string, string> = {}
      if (files.length > 0) {
        const fd = new FormData()
        fd.append('goal', goal)
        for (const f of files) fd.append('files[]', f)
        body = fd
      } else {
        body = JSON.stringify({ goal })
        headers['Content-Type'] = 'application/json'
      }
      const res = await apiFetch('/api/v1/tasks', { method: 'POST', headers, body })
      if (res.status === 401) {
        router.push('/login')
        return
      }
      if (res.ok) {
        const data = await res.json()
        router.push(`/tasks/${data.id as string}`)
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-2xl space-y-3">
      <Textarea
        value={goal}
        onChange={(e) => setGoal(e.target.value)}
        placeholder={t('placeholder')}
        className="min-h-[120px] resize-none text-base"
        aria-label={t('title')}
      />
      {fileError && <p className="text-destructive text-sm">{fileError}</p>}
      {micError && <p className="text-destructive text-sm">{micError}</p>}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
          >
            {t('attach')}
          </Button>
          {files.length > 0 && (
            <span className="text-sm text-muted-foreground">{files.length} file(s)</span>
          )}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ALLOWED_TYPES.join(',')}
            className="hidden"
            onChange={handleFileChange}
          />
          <TemplateModal onSelect={setGoal} />
          {hasMicSupport && (
            <div className="flex items-center gap-1">
              <Button
                type="button"
                variant={micState === 'recording' ? 'destructive' : 'outline'}
                size="sm"
                onClick={handleMicClick}
                disabled={micState === 'processing'}
                aria-label={
                  micState === 'recording'
                    ? t('recordStop')
                    : micState === 'processing'
                      ? t('transcribing')
                      : t('recordStart')
                }
              >
                {micState === 'processing' ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : micState === 'recording' ? (
                  <Square className="h-4 w-4" />
                ) : (
                  <Mic className="h-4 w-4" />
                )}
              </Button>
              {micState === 'recording' && (
                <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
              )}
            </div>
          )}
        </div>
        <Button type="submit" disabled={!goal.trim() || isSubmitting}>
          {t('submit')}
        </Button>
      </div>
    </form>
  )
}
