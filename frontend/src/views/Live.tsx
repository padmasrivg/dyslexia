import { useEffect, useMemo, useRef, useState } from 'react'
import { useAgent } from '../agent'
import { get, post } from '../api'
import {
  IconSpeaker,
  IconBook,
  IconEye,
  IconFile,
  IconCheck,
  speak,
} from './shared'

type ContentSource = 'pdf' | 'image' | 'text' | 'empty'

interface WordLookup {
  word: string
  syllables: string[]
  definition: string
}

export interface ScreenSentence {
  line_id: number
  text: string
  confidence?: number
  words: Array<{ text: string; confidence?: number }>
}

export interface ReadingWord {
  text: string
  clean: string
  globalIdx: number
}

export interface ReadingLine {
  id: number
  text: string
  words: ReadingWord[]
}

export function getReadingLines(text: string): ReadingLine[] {
  if (!text || !text.trim()) return []
  const paragraphs = text.split(/\r?\n/).map((p) => p.trim()).filter(Boolean)
  const lines: ReadingLine[] = []
  let globalWordCount = 0

  for (const para of paragraphs) {
    const sentenceMatches = para.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [para]
    for (const sent of sentenceMatches) {
      const trimmed = sent.trim()
      if (!trimmed) continue
      const rawWords = trimmed.split(/\s+/).filter(Boolean)
      if (rawWords.length <= 15) {
        const words = rawWords.map((w) => ({
          text: w,
          clean: w.replace(/[.,;!?()"'\[\]{}:]/g, ''),
          globalIdx: globalWordCount++,
        }))
        lines.push({ id: lines.length, text: trimmed, words })
      } else {
        for (let i = 0; i < rawWords.length; i += 11) {
          const slice = rawWords.slice(i, i + 11)
          const lineText = slice.join(' ')
          const words = slice.map((w) => ({
            text: w,
            clean: w.replace(/[.,;!?()"'\[\]{}:]/g, ''),
            globalIdx: globalWordCount++,
          }))
          lines.push({ id: lines.length, text: lineText, words })
        }
      }
    }
  }
  return lines
}

function getSyllables(word: string): string[] {
  const w = word.toLowerCase().trim()
  const map: Record<string, string[]> = {
    photosynthesis: ['pho', 'to', 'syn', 'the', 'sis'],
    plants: ['pla', 'nts'],
    plant: ['plant'],
    chlorophyll: ['chlo', 'ro', 'phyll'],
    absorb: ['ab', 'sorb'],
    carbon: ['car', 'bon'],
    dioxide: ['di', 'ox', 'ide'],
    aptitude: ['ap', 'ti', 'tude'],
    reasoning: ['rea', 'son', 'ing'],
    numerical: ['nu', 'mer', 'i', 'cal'],
    abstract: ['ab', 'stract'],
    verbal: ['ver', 'bal'],
    percentile: ['per', 'cen', 'tile'],
    score: ['score'],
    report: ['re', 'port'],
    question: ['ques', 'tion'],
    test: ['test'],
    alison: ['al', 'i', 'son'],
    padmasri: ['pad', 'ma', 'sri'],
    gandhi: ['gan', 'dhi'],
    confidence: ['con', 'fi', 'dence'],
    syllable: ['syl', 'la', 'ble'],
  }
  if (map[w]) return map[w]
  return w.length > 5 ? w.match(/.{1,3}/g) ?? [w] : [w]
}

export default function Live() {
  const { state: s, settings, setSettings, stop, busy } = useAgent()
  const box = useRef<HTMLDivElement>(null)
  const webcamRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  // Camera & Eye Tracking state
  const [cameraActive, setCameraActive] = useState(false)
  const [cameraError, setCameraError] = useState<string | null>(null)
  const [mirrorView, setMirrorView] = useState(true) // Mirror selfie view by default
  const [calibrated, setCalibrated] = useState(false)
  const [activeLineIdx, setActiveLineIdx] = useState<number>(0)
  const [activeWordText, setActiveWordText] = useState<string | null>(null)
  const [pupilCoords, setPupilCoords] = useState<{ x: number; y: number }>({ x: 50, y: 40 })
  const [gazeDocCoords, setGazeDocCoords] = useState<{ x: number; y: number } | null>(null)

  // Tracking sensitivity: 140 (Normal), 260 (High), 380 (Ultra)
  const [sensitivity, setSensitivity] = useState<number>(260)
  // Reading pacing assistant
  const [isAutoPaced, setIsAutoPaced] = useState<boolean>(false)
  const [autoPaceSpeed, setAutoPaceSpeed] = useState<number>(110) // WPM

  // Device discovery & Reading helpers
  const [deviceList, setDeviceList] = useState<{ monitors: Array<{ index: number }>; cameras: Array<{ index: number }> }>({ monitors: [], cameras: [] })
  const [showReadingRuler, setShowReadingRuler] = useState(true)
  const [isFrameFrozen, setIsFrameFrozen] = useState(false)
  const [cameraFlipped, setCameraFlipped] = useState(false)
  const [rulerY, setRulerY] = useState(120)

  // Synchronize cameraFlipped with backend state
  useEffect(() => {
    if (s && typeof s.camera_flipped === 'boolean') {
      setCameraFlipped(s.camera_flipped)
    }
  }, [s?.camera_flipped])

  const handleToggleFlip = async () => {
    const next = !cameraFlipped
    setCameraFlipped(next)
    try {
      const res = await post<{ ok: boolean; flipped: boolean }>('/api/camera/flip')
      if (res && typeof res.flipped === 'boolean') {
        setCameraFlipped(res.flipped)
      }
    } catch {
      /* ignore */
    }
  }

  const screenStreamRef = useRef<MediaStream | null>(null)
  const screenVideoRef = useRef<HTMLVideoElement | null>(null)
  const [isLocalScreenSharing, setIsLocalScreenSharing] = useState(false)
  const [localScreenWords, setLocalScreenWords] = useState<Array<{ text: string; confidence?: number }>>([])
  const [localScreenSentences, setLocalScreenSentences] = useState<ScreenSentence[]>([])
  const [isScanningScreen, setIsScanningScreen] = useState(false)
  const [screenSharingError, setScreenSharingError] = useState<string | null>(null)

  const captureAndProcessScreenFrame = async () => {
    const video = screenVideoRef.current
    if (!video || video.readyState < 2 || video.videoWidth === 0) return
    setIsScanningScreen(true)
    try {
      const canvas = document.createElement('canvas')
      const scale = Math.min(1, 1280 / video.videoWidth)
      canvas.width = Math.round(video.videoWidth * scale)
      canvas.height = Math.round(video.videoHeight * scale)
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
      const jpegData = canvas.toDataURL('image/jpeg', 0.8)

      const res = await post<{
        ok: boolean
        words: Array<{ text: string; confidence?: number; line_id?: number }>
        sentences?: Array<{ line_id: number; text: string; confidence?: number; words: Array<{ text: string }> }>
      }>('/api/screen/frame', { image: jpegData })

      if (res && res.ok) {
        if (Array.isArray(res.words)) setLocalScreenWords(res.words)
        if (Array.isArray(res.sentences) && res.sentences.length > 0) {
          setLocalScreenSentences(res.sentences)
        } else if (Array.isArray(res.words) && res.words.length > 0) {
          const grouped: Record<number, Array<{ text: string }>> = {}
          for (const w of res.words) {
            const lid = w.line_id ?? 0
            if (!grouped[lid]) grouped[lid] = []
            grouped[lid].push(w)
          }
          const sents = Object.entries(grouped).map(([lid, wrds]) => ({
            line_id: Number(lid),
            text: wrds.map((w) => w.text).join(' '),
            words: wrds,
          }))
          setLocalScreenSentences(sents)
        }
      }
    } catch {
      /* ignore frame push failure */
    } finally {
      setIsScanningScreen(false)
    }
  }

  const startScreenTracking = async () => {
    setScreenSharingError(null)
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { cursor: 'always' } as MediaTrackConstraints,
        audio: false,
      })
      screenStreamRef.current = stream
      if (screenVideoRef.current) {
        screenVideoRef.current.srcObject = stream
        void screenVideoRef.current.play()
      }
      setIsLocalScreenSharing(true)
      try {
        await post('/api/start', { mode: 'screen', monitor: settings.monitor })
      } catch {
        /* ignore */
      }
      const videoTrack = stream.getVideoTracks()[0]
      if (videoTrack) {
        videoTrack.onended = () => {
          stopScreenTracking()
        }
      }
      // Scan first frame once video feed establishes
      setTimeout(() => {
        void captureAndProcessScreenFrame()
      }, 500)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Screen capture was cancelled'
      setScreenSharingError(msg)
      setIsLocalScreenSharing(false)
    }
  }

  const stopScreenTracking = () => {
    if (screenStreamRef.current) {
      screenStreamRef.current.getTracks().forEach((t) => t.stop())
      screenStreamRef.current = null
    }
    if (screenVideoRef.current) {
      screenVideoRef.current.srcObject = null
    }
    setIsLocalScreenSharing(false)
    setLocalScreenWords([])
    setLocalScreenSentences([])
    void stop()
  }

  // Periodic real OCR on live screen video frames
  useEffect(() => {
    if (!isLocalScreenSharing) return
    const interval = setInterval(() => {
      void captureAndProcessScreenFrame()
    }, 2000)

    return () => {
      clearInterval(interval)
    }
  }, [isLocalScreenSharing])

  useEffect(() => {
    void get<{ monitors: Array<{ index: number }>; cameras: Array<{ index: number }> }>('/api/devices').then((d) => {
      if (d) setDeviceList(d)
    })
  }, [])

  const smoothPupilRef = useRef<{ x: number; y: number }>({ x: 50, y: 30 })
  const baselineEyeYRef = useRef<number | null>(null)
  const cameraStartTimeRef = useRef<number>(0)
  const lastAdvanceTimeRef = useRef<number>(0)
  const gazeDwellStartRef = useRef<number | null>(null)
  const activeLineIdxRef = useRef<number>(0)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const isProgrammaticScrollRef = useRef<boolean>(false)
  const [gazeFollowEnabled, setGazeFollowEnabled] = useState<boolean>(true)
  const [gazeDirectionState, setGazeDirectionState] = useState<'steady' | 'down' | 'up'>('steady')

  // Content & Upload state
  const [contentType, setContentType] = useState<ContentSource>('empty')
  const [uploadedUrl, setUploadedUrl] = useState<string | null>(null)
  const [uploadedFileName, setUploadedFileName] = useState<string>('')
  const [pdfExtractedText, setPdfExtractedText] = useState<string>('')
  const [customText, setCustomText] = useState<string>('')
  const [isPastingText, setIsPastingText] = useState(false)
  const [zoomLevel, setZoomLevel] = useState<number>(100)
  const [isLoadingPdf, setIsLoadingPdf] = useState(false)

  // Floating Meaning Popup
  const [activePopup, setActivePopup] = useState<{
    word: string
    syllables: string[]
    definition: string
    source?: string
    x: number
    y: number
  } | null>(null)
  const [popupLoading, setPopupLoading] = useState(false)
  const [speakingWord, setSpeakingWord] = useState<string | null>(null)

  // Start real browser camera via getUserMedia
  const startCamera = async () => {
    setCameraError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
        audio: false,
      })
      streamRef.current = stream
      if (webcamRef.current) {
        webcamRef.current.srcObject = stream
        await webcamRef.current.play()
      }
      cameraStartTimeRef.current = Date.now()
      baselineEyeYRef.current = null
      gazeDwellStartRef.current = null
      lastAdvanceTimeRef.current = Date.now()
      setCalibrated(false)
      setCameraActive(true)
      jumpToLineIndex(0)
      // Note: Mode 1 runs completely client-side in the browser. Do not invoke backend start() here
      // to avoid Windows camera device hardware contention!
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Could not open camera'
      setCameraError(msg)
      setCameraActive(false)
    }
  }

  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
    if (webcamRef.current) {
      webcamRef.current.srcObject = null
    }
    setCameraActive(false)
    setGazeDocCoords(null)
    setActiveWordText(null)
    setIsAutoPaced(false)
    baselineEyeYRef.current = null
    gazeDwellStartRef.current = null
    setGazeDirectionState('steady')
  }

  const activeText =
    contentType === 'pdf' && pdfExtractedText
      ? pdfExtractedText
      : contentType === 'text' && customText
      ? customText
      : ''

  const readingLines = useMemo(() => {
    return getReadingLines(activeText)
  }, [activeText])

  useEffect(() => {
    setActiveLineIdx(0)
    activeLineIdxRef.current = 0
  }, [activeText])

  const jumpToLineIndex = (idx: number) => {
    if (readingLines.length === 0) return
    const clamped = Math.max(0, Math.min(readingLines.length - 1, idx))
    setActiveLineIdx(clamped)
    activeLineIdxRef.current = clamped
    baselineEyeYRef.current = smoothPupilRef.current.y
    const el = document.getElementById(`reading-line-${clamped}`)
    if (el) {
      isProgrammaticScrollRef.current = true
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      setTimeout(() => {
        isProgrammaticScrollRef.current = false
      }, 500)
    }
  }

  // Synchronize reading line with user manual scroll (mouse wheel / trackpad / drag)
  const handleContainerScroll = () => {
    if (!scrollContainerRef.current || isProgrammaticScrollRef.current || readingLines.length === 0) return
    const container = scrollContainerRef.current
    const containerRect = container.getBoundingClientRect()
    // Target vertical reading line at around 38% from top of box
    const targetY = containerRect.top + containerRect.height * 0.38

    let closestIdx = 0
    let minDiff = Infinity

    for (let i = 0; i < readingLines.length; i++) {
      const el = document.getElementById(`reading-line-${i}`)
      if (el) {
        const r = el.getBoundingClientRect()
        const lineCenter = r.top + r.height / 2
        const diff = Math.abs(lineCenter - targetY)
        if (diff < minDiff) {
          minDiff = diff
          closestIdx = i
        }
      }
    }

    if (closestIdx !== activeLineIdxRef.current) {
      setActiveLineIdx(closestIdx)
      activeLineIdxRef.current = closestIdx
      baselineEyeYRef.current = smoothPupilRef.current.y
    }
  }

  const nextLine = () => {
    jumpToLineIndex(activeLineIdxRef.current + 1)
  }

  const prevLine = () => {
    jumpToLineIndex(activeLineIdxRef.current - 1)
  }


  // Keyboard navigation for line-by-line reading
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement)?.tagName)) return
      if (e.key === 'ArrowDown' || e.key === 'ArrowRight' || e.key === ' ') {
        e.preventDefault()
        nextLine()
      } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
        e.preventDefault()
        prevLine()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [activeLineIdx, readingLines.length])

  // Auto-Paced Line-by-Line Reading Guide
  useEffect(() => {
    if (!isAutoPaced || readingLines.length === 0) return
    const msPerLine = Math.max(2500, Math.round((70 / autoPaceSpeed) * 5000))
    const interval = setInterval(() => {
      setActiveLineIdx((prev) => {
        const next = (prev + 1) % readingLines.length
        const el = document.getElementById(`reading-line-${next}`)
        el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
        return next
      })
    }, msPerLine)
    return () => clearInterval(interval)
  }, [isAutoPaced, autoPaceSpeed, readingLines.length])

  // Calibrate gaze baseline to line 0
  const handleCalibrateGaze = () => {
    baselineEyeYRef.current = smoothPupilRef.current.y
    gazeDwellStartRef.current = null
    lastAdvanceTimeRef.current = Date.now()
    setCalibrated(true)
    setGazeDirectionState('steady')
    jumpToLineIndex(0)
  }

  const loadSamplePassage = () => {
    setContentType('text')
    setCustomText(
      'Plants use sunlight, water, and carbon dioxide to make food and oxygen through photosynthesis.\nInside leaves, chlorophyll absorbs light energy so plants can grow strong.\nRoots absorb vital nutrients and water from the soil.\nHealthy leaves release fresh oxygen back into the atmosphere for all living creatures.'
    )
    setUploadedFileName('Sample Passage - Plant Science')
  }

  // Real-time canvas eye & pupil tracker on video frames
  useEffect(() => {
    if (!cameraActive) return
    let animId: number
    const processFrame = () => {
      const video = webcamRef.current
      const canvas = canvasRef.current
      if (video && canvas && video.readyState >= 2) {
        const ctx = canvas.getContext('2d', { willReadFrequently: true })
        if (ctx) {
          if (mirrorView) {
            ctx.save()
            ctx.scale(-1, 1)
            ctx.drawImage(video, -160, 0, 160, 120)
            ctx.restore()
          } else {
            ctx.drawImage(video, 0, 0, 160, 120)
          }

          const frame = ctx.getImageData(0, 0, 160, 120)
          const d = frame.data

          // Robust Eye Tracking: Search left and right eye quadrants
          // Specifically in the upper-middle facial zone (Y: 20% to 38%)
          // This avoids cheeks, mouth, chin, and side hair
          const findEyePupil = (xStartFrac: number, xEndFrac: number, yStartFrac: number, yEndFrac: number) => {
            const startX = Math.floor(160 * xStartFrac)
            const endX = Math.floor(160 * xEndFrac)
            const startY = Math.floor(120 * yStartFrac)
            const endY = Math.floor(120 * yEndFrac)

            let minB = 255
            for (let y = startY; y < endY; y += 2) {
              for (let x = startX; x < endX; x += 2) {
                const i = (y * 160 + x) * 4
                const b = d[i] * 0.299 + d[i + 1] * 0.587 + d[i + 2] * 0.114
                if (b < minB) minB = b
              }
            }

            let sumX = 0
            let sumY = 0
            let totalWeight = 0
            const threshold = minB + 16

            for (let y = startY; y < endY; y++) {
              for (let x = startX; x < endX; x++) {
                const i = (y * 160 + x) * 4
                const b = d[i] * 0.299 + d[i + 1] * 0.587 + d[i + 2] * 0.114
                if (b <= threshold) {
                  const w = threshold - b + 1
                  sumX += x * w
                  sumY += y * w
                  totalWeight += w
                }
              }
            }

            if (totalWeight > 0) {
              return {
                x: (sumX / totalWeight / 160) * 100,
                y: (sumY / totalWeight / 120) * 100,
              }
            }
            return null
          }

          const leftPupil = findEyePupil(0.28, 0.48, 0.28, 0.50)
          const rightPupil = findEyePupil(0.52, 0.72, 0.28, 0.50)

          let rawX = 50
          let rawY = 36
          if (leftPupil && rightPupil) {
            rawX = (leftPupil.x + rightPupil.x) / 2
            rawY = (leftPupil.y + rightPupil.y) / 2
          } else if (leftPupil) {
            rawX = leftPupil.x
            rawY = leftPupil.y
          } else if (rightPupil) {
            rawX = rightPupil.x
            rawY = rightPupil.y
          }

          smoothPupilRef.current.x += (rawX - smoothPupilRef.current.x) * 0.22
          smoothPupilRef.current.y += (rawY - smoothPupilRef.current.y) * 0.22

          setPupilCoords({
            x: smoothPupilRef.current.x,
            y: smoothPupilRef.current.y,
          })

          const now = Date.now()

          // Auto-calibrate baseline at initial eye position after 600ms
          if (baselineEyeYRef.current === null && now - cameraStartTimeRef.current > 600) {
            baselineEyeYRef.current = smoothPupilRef.current.y
            setCalibrated(true)
          }

          // Relative Saccade Line Advancement (Step-wise reading guide)
          // NEVER jump across multiple lines or teleport down the document.
          // Advances strictly one line at a time when downward reading gaze is detected.
          if (baselineEyeYRef.current !== null && gazeFollowEnabled && readingLines.length > 0) {
            const dy = smoothPupilRef.current.y - baselineEyeYRef.current
            // Sensitivity adjusts the required downward gaze movement
            const downThreshold = Math.max(1.8, 3.2 - (sensitivity / 40))
            const upThreshold = -Math.max(1.8, 3.2 - (sensitivity / 40))

            if (dy > downThreshold) {
              setGazeDirectionState('down')
              if (!gazeDwellStartRef.current) {
                gazeDwellStartRef.current = now
              } else if (now - gazeDwellStartRef.current > 380 && now - lastAdvanceTimeRef.current > 700) {
                // Reader reached line end and glanced down: advance ONE line
                const next = Math.min(readingLines.length - 1, activeLineIdxRef.current + 1)
                jumpToLineIndex(next)
                lastAdvanceTimeRef.current = now
                gazeDwellStartRef.current = null
              }
            } else if (dy < upThreshold) {
              setGazeDirectionState('up')
              if (!gazeDwellStartRef.current) {
                gazeDwellStartRef.current = now
              } else if (now - gazeDwellStartRef.current > 380 && now - lastAdvanceTimeRef.current > 700) {
                // Reader glanced up to re-read: step back ONE line
                const prevIdx = Math.max(0, activeLineIdxRef.current - 1)
                jumpToLineIndex(prevIdx)
                lastAdvanceTimeRef.current = now
                gazeDwellStartRef.current = null
              }
            } else {
              setGazeDirectionState('steady')
              gazeDwellStartRef.current = null
              // Gently adapt baseline to steady gaze level to account for posture shifts without line jumps
              baselineEyeYRef.current += (smoothPupilRef.current.y - baselineEyeYRef.current) * 0.03
            }
          }

        }
      }
      animId = requestAnimationFrame(processFrame)
    }

    animId = requestAnimationFrame(processFrame)
    return () => cancelAnimationFrame(animId)
  }, [cameraActive, sensitivity, mirrorView, gazeFollowEnabled, readingLines.length])


  // Handle local file uploads
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    setUploadedFileName(file.name)
    setActivePopup(null)
    setPdfExtractedText('')
    setCustomText('')

    if (file.type === 'application/pdf' || file.name.endsWith('.pdf')) {
      setContentType('pdf')
      const localPdfUrl = URL.createObjectURL(file)
      setUploadedUrl(localPdfUrl)
      setIsLoadingPdf(true)

      try {
        const formData = new FormData()
        formData.append('file', file)
        const res = await fetch('/api/pdf/extract', {
          method: 'POST',
          body: formData,
        })
        const data = await res.json()
        if (data.ok && data.text) {
          setPdfExtractedText(data.text)
        } else {
          setPdfExtractedText(
            `PDF Document: "${file.name}".\n\nDyslexia Vision is ready to follow your reading. Click any word on this page to immediately hear pronunciation and view syllables.`
          )
        }
      } catch {
        setPdfExtractedText(
          `Reading Material: "${file.name}".\n\nClick any word to hear pronunciation and view clear syllables.`
        )
      } finally {
        setIsLoadingPdf(false)
      }
      window.open(localPdfUrl, '_blank')
    } else if (file.type.startsWith('image/')) {
      setContentType('image')
      setUploadedUrl(URL.createObjectURL(file))
    } else {
      setContentType('text')
      const reader = new FileReader()
      reader.onload = (event) => {
        setCustomText((event.target?.result as string) || '')
      }
      reader.readAsText(file)
    }
  }

  // Cancel / Close opened document
  const handleCancelDocument = () => {
    setContentType('empty')
    setUploadedUrl(null)
    setUploadedFileName('')
    setPdfExtractedText('')
    setCustomText('')
    setActivePopup(null)
    setActiveWordText(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const speakWord = (word: string, def?: string) => {
    setSpeakingWord(word)
    speak(def ? `${word}. ${def}` : word, () => setSpeakingWord(null))
  }

  const showWordMeaning = async (clean: string, clientX: number, clientY: number, sentenceContext = '') => {
    if (!clean) return
    const container = box.current?.getBoundingClientRect()
    const relX = container ? Math.min(container.width - 290, Math.max(10, clientX - container.left - 80)) : clientX
    const relY = container ? clientY - container.top + 20 : clientY + 20

    const initialSyllables = getSyllables(clean)
    setActivePopup({
      word: clean,
      syllables: initialSyllables,
      definition: 'Asking Gemini AI for simple explanation...',
      source: 'gemini',
      x: relX,
      y: relY,
    })
    setPopupLoading(true)

    let finalDef = `${clean.charAt(0).toUpperCase() + clean.slice(1)} is an important word used in this sentence.`
    let defSource = 'gemini'
    try {
      const lineCtx = sentenceContext || readingLines[activeLineIdx]?.text || ''
      const res = await get<WordLookup & { source?: string }>(
        `/api/explain/${encodeURIComponent(clean)}?context=${encodeURIComponent(lineCtx)}`
      )
      if (res && res.definition) {
        finalDef = res.definition
        if (res.source) defSource = res.source
      }
    } catch {
      /* fallback */
    } finally {
      setPopupLoading(false)
      setActivePopup({
        word: clean,
        syllables: initialSyllables,
        definition: finalDef,
        source: defSource,
        x: relX,
        y: relY,
      })
      // Intentionally do NOT auto-speak so the reader can read silently in peace.
    }
  }


  if (!s) return null

  const isCameraRunning = s.running && s.input.mode === 'camera'
  const cameraWords = isCameraRunning ? (s.words || []) : []
  const cameraSentences: ScreenSentence[] = useMemo<ScreenSentence[]>(() => {
    if (!isCameraRunning) return []
    if (Array.isArray(s.sentences) && s.sentences.length > 0) {
      return s.sentences as ScreenSentence[]
    }
    if (Array.isArray(s.words) && s.words.length > 0) {
      const grouped: Record<number, Array<{ text: string; confidence?: number }>> = {}
      for (const w of s.words) {
        const lid = (w as any).line_id ?? 0
        if (!grouped[lid]) grouped[lid] = []
        grouped[lid].push(w)
      }
      return Object.entries(grouped).map(([lid, wrds]) => ({
        line_id: Number(lid),
        text: wrds.map((w) => w.text).join(' '),
        words: wrds,
      }))
    }
    return []
  }, [isCameraRunning, s.sentences, s.words])

  const isScreenRunning = s.running && s.input.mode === 'screen'
  const activeScreenRunning = isLocalScreenSharing || isScreenRunning
  const screenWords = isLocalScreenSharing ? localScreenWords : (isScreenRunning ? (s.words || []) : [])

  return (
    <div className="flex flex-col gap-6 animate-fade-in">
      {/* Hidden File Input */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileUpload}
        accept=".pdf, image/*, .txt, .md"
        className="hidden"
      />
      {/* Offscreen frame processing canvas */}
      <canvas ref={canvasRef} width="160" height="120" className="hidden" />

      {/* Top Reading Mode Navigation Switcher */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-page rounded-2xl border border-rule">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setSettings({ mode: 'demo' })}
            className={`btn btn-sm px-4 py-2 font-bold text-xs flex items-center gap-2 rounded-xl transition-all ${
              settings.mode === 'demo'
                ? 'bg-gblue text-white shadow-xs'
                : 'bg-surface text-ink hover:bg-page border border-rule'
            }`}
          >
            <IconBook className="w-4 h-4" />
            <span>Interactive Document (PDF & Text)</span>
          </button>

          <button
            type="button"
            onClick={() => setSettings({ mode: 'camera' })}
            className={`btn btn-sm px-4 py-2 font-bold text-xs flex items-center gap-2 rounded-xl transition-all ${
              settings.mode === 'camera'
                ? 'bg-gblue text-white shadow-xs'
                : 'bg-surface text-ink hover:bg-page border border-rule'
            }`}
          >
            <IconEye className="w-4 h-4" />
            <span>Printed Books & Webcam</span>
          </button>

          <button
            type="button"
            onClick={() => setSettings({ mode: 'screen' })}
            className={`btn btn-sm px-4 py-2 font-bold text-xs flex items-center gap-2 rounded-xl transition-all ${
              settings.mode === 'screen'
                ? 'bg-gblue text-white shadow-xs'
                : 'bg-surface text-ink hover:bg-page border border-rule'
            }`}
          >
            <IconFile className="w-4 h-4" />
            <span>Computer Screen</span>
          </button>
        </div>

        <span className="text-xs font-semibold text-muted px-2">
          Current Mode: <strong className="text-ink">{
            settings.mode === 'demo'
              ? 'Interactive Document'
              : settings.mode === 'camera'
              ? 'Printed Books & Webcam'
              : 'Computer Screen'
          }</strong>
        </span>
      </div>

      {/* =========================================================================
          MODE 1: INTERACTIVE READING ROOM (PDFs, Images, Custom Text)
      ========================================================================= */}
      {settings.mode === 'demo' && (
        <div className="grid gap-6 lg:grid-cols-12 items-start animate-fade-in">
          {/* Main Stage: Reading Studio (8 cols) */}
          <div className="lg:col-span-8 flex flex-col gap-4">
            <div className="reading-box p-6 relative" ref={box}>
              {/* Top Document Toolbar */}
              <div className="flex flex-wrap items-center justify-between gap-3 pb-4 mb-4 border-b border-rule">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-bold text-muted uppercase mr-1">Document:</span>

                  <button
                    type="button"
                    className="btn btn-primary btn-sm text-xs py-1 px-3 text-white font-bold"
                    onClick={() => fileInputRef.current?.click()}
                    title="Upload a PDF, image, or text file"
                  >
                    <span>Upload File (PDF / Image / Text)</span>
                  </button>

                  <button
                    type="button"
                    className={`btn btn-sm text-xs py-1 px-3 ${contentType === 'text' ? 'btn-google text-white' : 'bg-page text-ink'}`}
                    onClick={() => setIsPastingText(!isPastingText)}
                  >
                    <span>Paste Text</span>
                  </button>

                  <button
                    type="button"
                    className="btn btn-sm text-xs py-1 px-3 bg-surface hover:bg-page border border-rule text-ink font-semibold"
                    onClick={loadSamplePassage}
                    title="Load sample passage about plants and science"
                  >
                    <span>Try Sample Passage</span>
                  </button>

                  {(contentType === 'pdf' || contentType === 'image' || contentType === 'text' || uploadedFileName) && (
                    <button
                      type="button"
                      className="btn btn-sm text-xs py-1 px-3 bg-gred-light text-gred border-gred/40 hover:bg-gred hover:text-white font-bold"
                      onClick={handleCancelDocument}
                      title="Close document"
                    >
                      <span>Close Document</span>
                    </button>
                  )}
                </div>

                {/* Zoom Controls */}
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    className="btn btn-sm text-xs py-1 px-2.5 bg-page"
                    onClick={() => setZoomLevel((z) => Math.max(70, z - 15))}
                    title="Zoom out"
                  >
                    -
                  </button>
                  <span className="text-xs num font-semibold text-muted px-1">{zoomLevel}%</span>
                  <button
                    type="button"
                    className="btn btn-sm text-xs py-1 px-2.5 bg-page"
                    onClick={() => setZoomLevel((z) => Math.min(200, z + 15))}
                    title="Zoom in"
                  >
                    +
                  </button>
                </div>
              </div>

              {/* Document Status Notice */}
              {uploadedFileName && (
                <div className="mb-3 px-3 py-2 rounded-lg bg-gblue-light/50 border border-gblue/30 flex items-center justify-between text-xs">
                  <div>
                    <span className="font-bold text-ink mr-2">Opened File:</span>
                    <span className="font-medium text-gblue">{uploadedFileName}</span>
                    {contentType === 'pdf' && (
                      <span className="text-muted ml-2">(Opened in new page tab + detected below)</span>
                    )}
                  </div>
                  <button
                    type="button"
                    className="font-bold text-gred hover:underline"
                    onClick={handleCancelDocument}
                  >
                    Close Document
                  </button>
                </div>
              )}

              {/* Paste Text Drawer */}
              {isPastingText && (
                <div className="mb-4 p-4 rounded-xl bg-page border border-rule animate-fade-in">
                  <label className="block text-xs font-bold text-ink mb-1.5" htmlFor="paste-area">
                    Type or paste the reading passage:
                  </label>
                  <textarea
                    id="paste-area"
                    rows={4}
                    className="w-full p-3 rounded-lg border border-rule bg-white text-ink text-sm font-sans focus:outline-gblue"
                    placeholder="Paste text here..."
                    value={customText}
                    onChange={(e) => setCustomText(e.target.value)}
                  />
                  <div className="flex items-center gap-2 mt-2">
                    <button
                      type="button"
                      className="btn btn-sm btn-primary text-xs"
                      onClick={() => {
                        setContentType('text')
                        setIsPastingText(false)
                      }}
                    >
                      Open in Reading Room
                    </button>
                    <button
                      type="button"
                      className="btn btn-sm bg-surface text-xs"
                      onClick={() => setIsPastingText(false)}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {/* Floating Pupil Reticle */}
              {cameraActive && gazeDocCoords && (
                <div
                  className="gaze-reticle"
                  style={{ left: `${gazeDocCoords.x}px`, top: `${gazeDocCoords.y}px` }}
                  aria-hidden="true"
                >
                  <div className="gaze-pupil" />
                  {activeWordText && (
                    <span className="absolute -top-6 left-1/2 -translate-x-1/2 px-2 py-0.5 rounded-full bg-gblue text-white text-[11px] font-bold whitespace-nowrap shadow-md pointer-events-none">
                      {activeWordText}
                    </span>
                  )}
                </div>
              )}

              {/* Floating Word Meaning Popup */}
              {activePopup && (
                <div
                  className="absolute z-50 p-4 rounded-xl bg-white border-2 border-gblue shadow-2xl max-w-sm transition-all animate-fade-in"
                  style={{ top: `${activePopup.y}px`, left: `${activePopup.x}px` }}
                >
                  <div className="flex items-center justify-between pb-2 border-b border-rule">
                    <div className="flex items-center gap-2">
                      <h4 className="text-lg font-extrabold text-ink">{activePopup.word}</h4>
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-gblue-light text-gblue border border-gblue/30 flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-gblue animate-pulse" />
                        Gemini AI
                      </span>
                      {speakingWord === activePopup.word && (
                        <span className="text-xs font-bold text-ggreen animate-pulse">Playing voice...</span>
                      )}
                    </div>
                    <button
                      type="button"
                      className="h-6 w-6 rounded-full bg-page hover:bg-rule text-xs font-bold text-muted hover:text-ink flex items-center justify-center ml-2 cursor-pointer transition-colors"
                      onClick={() => setActivePopup(null)}
                      title="Close"
                    >
                      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <path d="M18 6L6 18M6 6l12 12" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </button>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5 my-2.5">
                    <span className="text-[10px] uppercase font-bold text-muted mr-1">Syllables:</span>
                    {activePopup.syllables.map((syl, i) => (
                      <span key={i} className="px-2 py-0.5 rounded-md bg-gblue-light text-gblue font-extrabold text-xs">
                        {syl}
                        {i < activePopup.syllables.length - 1 && <span className="ml-1 text-muted">&bull;</span>}
                      </span>
                    ))}
                  </div>

                  <div className="p-2.5 rounded-lg bg-page border border-rule min-h-[46px] flex items-center">
                    {popupLoading ? (
                      <p className="text-xs text-muted italic flex items-center gap-1.5 animate-pulse">
                        <span className="w-2 h-2 rounded-full bg-gblue animate-ping shrink-0" />
                        Asking Gemini for a simple explanation...
                      </p>
                    ) : (
                      <p className="text-xs text-ink leading-relaxed font-medium">
                        {activePopup.definition}
                      </p>
                    )}
                  </div>

                  <div className="flex items-center gap-2 mt-3">
                    <button
                      type="button"
                      className="btn btn-primary btn-sm flex-1 text-xs font-bold text-white py-1 cursor-pointer"
                      onClick={() => speakWord(activePopup.word, activePopup.definition)}
                    >
                      <span>Listen Again</span>
                    </button>
                    <button
                      type="button"
                      className="btn btn-sm text-xs bg-page py-1 cursor-pointer"
                      onClick={() => setActivePopup(null)}
                    >
                      <span>Dismiss</span>
                    </button>
                  </div>
                </div>
              )}


              {/* Sticky Reading Ruler Navigation Bar */}
              {activeText && (contentType === 'text' || contentType === 'pdf') && (
                <div className="mb-3 p-2.5 rounded-xl bg-white border border-gblue/40 shadow-xs flex flex-wrap items-center justify-between gap-2 select-none">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="flex h-2.5 w-2.5 rounded-full bg-gblue animate-pulse shrink-0" />
                    <span className="text-xs font-bold text-ink whitespace-nowrap">
                      Line <span className="text-gblue font-extrabold text-sm">{activeLineIdx + 1}</span> of {readingLines.length}
                    </span>
                    <span className="text-xs text-muted font-medium truncate max-w-[280px] hidden md:inline">
                      &ldquo;{readingLines[activeLineIdx]?.text || ''}&rdquo;
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <button
                      type="button"
                      onClick={prevLine}
                      disabled={activeLineIdx <= 0}
                      className="px-2.5 py-1 text-xs font-bold rounded-lg bg-page border border-rule hover:bg-surface disabled:opacity-40 cursor-pointer text-ink"
                      title="Move to Previous Line (Up Arrow)"
                    >
                      Prev Line
                    </button>
                    <button
                      type="button"
                      onClick={nextLine}
                      disabled={activeLineIdx >= readingLines.length - 1}
                      className="px-3 py-1 text-xs font-bold rounded-lg bg-gblue text-white hover:bg-gblue/90 disabled:opacity-40 cursor-pointer shadow-xs"
                      title="Move to Next Line (Down Arrow or Space)"
                    >
                      Next Line
                    </button>
                    <button
                      type="button"
                      onClick={() => jumpToLineIndex(activeLineIdx)}
                      className="px-2.5 py-1 text-xs font-semibold rounded-lg bg-page border border-rule hover:bg-surface cursor-pointer text-muted hover:text-ink"
                      title="Center active reading line in viewport"
                    >
                      Center Line
                    </button>
                  </div>
                </div>
              )}

              {/* Vertically Scrollable Reading Canvas */}
              <div
                ref={scrollContainerRef}
                onScroll={handleContainerScroll}
                className="max-h-[540px] overflow-y-auto custom-scrollbar pr-2 select-text"
              >
                {isLoadingPdf && (
                  <div className="py-8 text-center text-sm text-muted">
                    Extracting words from PDF for interactive reading...
                  </div>
                )}

                {contentType === 'image' && uploadedUrl && (
                  <div className="flex flex-col gap-3">
                    <div className="flex items-center justify-between text-xs text-muted pb-1">
                      <span className="font-bold text-ink">Image Document: {uploadedFileName}</span>
                      <span>Click anywhere on the image to inspect words</span>
                    </div>
                    <div
                      className="p-3 rounded-xl bg-page border border-rule flex justify-center overflow-auto cursor-pointer relative"
                      onClick={(e) => {
                        const text = window.getSelection()?.toString().trim()
                        const targetWord = text || 'Report'
                        showWordMeaning(targetWord, e.clientX, e.clientY)
                      }}
                    >
                      <img
                        src={uploadedUrl}
                        alt={uploadedFileName}
                        style={{ width: `${zoomLevel}%` }}
                        className="rounded-lg shadow-xs object-contain transition-all"
                      />
                    </div>
                  </div>
                )}

                {/* EMPTY STATE */}
                {!activeText && contentType !== 'image' && !isLoadingPdf && (
                  <div className="flex flex-col items-center justify-center py-14 px-6 text-center border-2 border-dashed border-rule rounded-xl bg-page/40 min-h-[280px]">
                    <div className="w-14 h-14 rounded-2xl bg-gblue-light text-gblue flex items-center justify-center mb-4 shadow-xs">
                      <IconBook className="w-7 h-7" />
                    </div>
                    <h3 className="text-xl font-bold text-ink mb-1.5">No Reading Material Loaded</h3>
                    <p className="text-sm text-muted max-w-md mb-6 leading-relaxed">
                      Upload a file (PDF, image, or text) or paste a reading passage to start interactive reading with eye-gaze tracking and live assistance.
                    </p>
                    <div className="flex flex-wrap items-center justify-center gap-3">
                      <button
                        type="button"
                        className="btn btn-primary text-xs font-bold text-white py-2 px-4 shadow-xs"
                        onClick={() => fileInputRef.current?.click()}
                      >
                        <span>Upload File (PDF / Image / Text)</span>
                      </button>
                      <button
                        type="button"
                        className="btn bg-white border border-rule text-ink text-xs font-semibold py-2 px-4 shadow-xs"
                        onClick={() => setIsPastingText(true)}
                      >
                        <span>Paste Text</span>
                      </button>
                      <button
                        type="button"
                        className="btn bg-white border border-rule text-ink text-xs font-semibold py-2 px-4 shadow-xs"
                        onClick={loadSamplePassage}
                      >
                        <span>Try Sample Passage</span>
                      </button>
                    </div>
                  </div>
                )}

                {/* TEXT OR EXTRACTED PDF READING PASSAGE - LINE BY LINE */}
                {activeText && (contentType === 'text' || contentType === 'pdf') && (
                  <div className="reading-passage-content p-2 min-h-[260px] flex flex-col gap-1.5 select-text">
                    {readingLines.map((line) => {
                      const isCurrent = activeLineIdx === line.id
                      return (
                        <div
                          key={line.id}
                          id={`reading-line-${line.id}`}
                          className={`reading-line group relative flex items-center justify-between rounded-xl px-4 py-2.5 transition-all duration-150 cursor-pointer ${
                            isCurrent
                              ? 'bg-gblue-light/85 border-l-4 border-gblue shadow-xs font-semibold ring-1 ring-gblue/30'
                              : 'hover:bg-page border-l-4 border-transparent opacity-80 hover:opacity-100'
                          }`}
                          onClick={() => {
                            jumpToLineIndex(line.id)
                          }}
                        >

                          {/* Active Line Text */}
                          <div
                            className="flex-1 flex flex-wrap items-center gap-1.5 leading-relaxed text-ink"
                            style={{ fontSize: `${(zoomLevel / 100) * 1.15}rem` }}
                          >
                            {isCurrent && (
                              <span className="inline-block w-2 h-2 rounded-full bg-gblue animate-pulse mr-1 shrink-0" aria-hidden="true" />
                            )}
                            {line.words.map((w, wIdx) => {
                              return (
                                <span
                                  key={wIdx}
                                  className="word-token px-1.5 py-0.5 rounded-md hover:bg-gblue/20 hover:text-gblue cursor-pointer transition-colors"
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    setActiveLineIdx(line.id)
                                    baselineEyeYRef.current = smoothPupilRef.current.y
                                    showWordMeaning(w.clean, e.clientX, e.clientY, line.text)
                                  }}
                                  title="Click to view syllables and Gemini AI definition"
                                >
                                  {w.text}
                                </span>
                              )
                            })}

                          </div>

                          {/* Line Audio button: Listen on demand */}
                          <button
                            type="button"
                            className={`p-1.5 rounded-lg text-muted hover:text-gblue hover:bg-white transition-all ml-2 shrink-0 cursor-pointer ${
                              isCurrent ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                            }`}
                            title="Listen to this line read aloud"
                            onClick={(e) => {
                              e.stopPropagation()
                              speak(line.text)
                            }}
                          >
                            <IconSpeaker className="w-4 h-4" />
                          </button>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>

              {/* Reading Controls: Line-by-Line Navigation */}
              <div className="flex flex-wrap items-center justify-between gap-3 pt-3 mt-3 border-t border-rule">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className="btn btn-sm text-xs bg-page hover:bg-surface font-bold text-ink py-1.5 px-3 disabled:opacity-40 cursor-pointer"
                    onClick={prevLine}
                    disabled={readingLines.length === 0 || activeLineIdx <= 0}
                    title="Previous line (or press Up Arrow)"
                  >
                    &uarr; Previous Line
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm text-xs font-bold text-white py-1.5 px-3 shadow-xs disabled:opacity-40 cursor-pointer"
                    onClick={nextLine}
                    disabled={readingLines.length === 0 || activeLineIdx >= readingLines.length - 1}
                    title="Next line (or press Down Arrow / Space)"
                  >
                    Next Line &darr;
                  </button>
                  <span className="text-[11px] text-muted hidden sm:inline">
                    (Line {readingLines.length > 0 ? activeLineIdx + 1 : 0} of {readingLines.length} &bull; Use <kbd className="px-1.5 py-0.5 rounded bg-page border border-rule text-[11px] font-mono font-bold">&darr;</kbd> / <kbd className="px-1.5 py-0.5 rounded bg-page border border-rule text-[11px] font-mono font-bold">Space</kbd> to advance)
                  </span>
                </div>

                <div className="flex items-center gap-2.5">
                  <div className="flex items-center rounded-lg border border-rule bg-page overflow-hidden">
                    <button
                      type="button"
                      className={`btn btn-sm text-xs py-1.5 px-3 font-semibold rounded-none border-none cursor-pointer ${isAutoPaced ? 'bg-ggreen text-white' : 'bg-transparent text-ink'}`}
                      onClick={() => setIsAutoPaced(!isAutoPaced)}
                      title="Automatically guide line-by-line down the passage"
                    >
                      {isAutoPaced ? 'Auto-Guide Line: Active' : 'Auto-Guide Line Pace'}
                    </button>
                    {isAutoPaced && (
                      <select
                        value={autoPaceSpeed}
                        onChange={(e) => setAutoPaceSpeed(Number(e.target.value))}
                        className="text-[11px] py-1 px-1.5 bg-page border-l border-rule text-ink font-bold cursor-pointer"
                        title="Reading speed in words per minute"
                      >
                        <option value={80}>80 WPM (Slow)</option>
                        <option value={110}>110 WPM (Comfortable)</option>
                        <option value={150}>150 WPM (Brisk)</option>
                      </select>
                    )}
                  </div>

                  <div className="flex items-center gap-1 text-xs">
                    <span className="text-muted text-[11px] font-semibold">Eye Sensitivity:</span>
                    <select
                      value={sensitivity}
                      onChange={(e) => setSensitivity(Number(e.target.value))}
                      className="text-xs p-1 rounded border border-rule bg-page text-ink font-bold cursor-pointer"
                      title="Eye tracking sensitivity"
                    >
                      <option value={140}>Normal</option>
                      <option value={260}>High (Default)</option>
                      <option value={380}>Ultra High</option>
                    </select>
                  </div>
                </div>
              </div>

              <p className="text-xs text-muted mt-2">
                Click or hover any line to highlight. Use eye tracking or arrow keys to follow lines smoothly without losing your place.
              </p>
            </div>
          </div>

          {/* ASIDE STAGE: Live Eye Tracker Camera (4 cols) */}
          <div className="lg:col-span-4 flex flex-col gap-4">
            <div className="google-card p-4">
              <div className="flex items-center justify-between pb-3 mb-3 border-b border-rule">
                <div className="flex items-center gap-2">
                  <span className={`flex h-2.5 w-2.5 rounded-full ${cameraActive ? 'bg-ggreen animate-pulse' : 'bg-control'}`} />
                  <h3 className="font-bold text-ink text-sm">Live Eye Tracker Camera</h3>
                </div>
                <div className="flex items-center gap-2">
                  {cameraActive && (
                    <button
                      type="button"
                      onClick={() => setMirrorView(!mirrorView)}
                      className="text-[11px] font-semibold px-2 py-0.5 rounded-full border border-rule bg-page hover:bg-surface text-ink transition-colors"
                      title="Toggle Camera Mirror View"
                    >
                      {mirrorView ? 'Mirror: On' : 'Mirror: Off'}
                    </button>
                  )}
                  <span className={`tag text-xs font-bold ${cameraActive ? 'tag-google-green' : 'bg-page text-muted'}`}>
                    {cameraActive ? 'CAMERA ON' : 'CAMERA OFF'}
                  </span>
                </div>
              </div>

              {/* Real-Time Camera Feed Viewport */}
              <div className="camera-aside-frame aspect-video w-full flex items-center justify-center bg-black relative rounded-xl overflow-hidden">
                <video
                  ref={webcamRef}
                  autoPlay
                  playsInline
                  muted
                  className={`h-full w-full object-cover transition-transform ${cameraActive ? 'block' : 'hidden'}`}
                  style={mirrorView ? { transform: 'scaleX(-1)' } : undefined}
                />

                {cameraActive && (
                  <div className="camera-hud-overlay">
                    <div className="flex items-center justify-between text-[11px] font-bold text-white bg-black/70 px-2 py-1 rounded">
                      <span className="flex items-center gap-1.5">
                        <span className={`w-2 h-2 rounded-full ${calibrated ? 'bg-ggreen animate-pulse' : 'bg-gyellow'}`} />
                        <span>{calibrated ? 'EYE TRACK: CALIBRATED' : 'ALIGNING EYES'}</span>
                      </span>
                      <span className="text-ggreen text-[10px]">{mirrorView ? 'MIRROR VIEW' : 'REAR VIEW'}</span>
                    </div>

                    {/* Left Eye Guide Box */}
                    <div
                      className="absolute pointer-events-none border border-white/40 border-dashed rounded-lg flex items-center justify-center"
                      style={{ left: '28%', top: '28%', width: '20%', height: '22%' }}
                      title="Left Eye Zone"
                    >
                      <span className="text-[9px] text-white/50 font-mono">L</span>
                    </div>
                    {/* Right Eye Guide Box */}
                    <div
                      className="absolute pointer-events-none border border-white/40 border-dashed rounded-lg flex items-center justify-center"
                      style={{ left: '52%', top: '28%', width: '20%', height: '22%' }}
                      title="Right Eye Zone"
                    >
                      <span className="text-[9px] text-white/50 font-mono">R</span>
                    </div>


                    {/* Detected Pupil / Gaze Reticle */}
                    <div
                      className="absolute pointer-events-none transition-all duration-75"
                      style={{ left: `${pupilCoords.x}%`, top: `${pupilCoords.y}%`, transform: 'translate(-50%, -50%)' }}
                    >
                      <div className="h-8 w-8 rounded-full border-2 border-gblue border-dashed flex items-center justify-center">
                        <div className="h-2 w-2 rounded-full bg-gblue shadow-xs" />
                      </div>
                    </div>

                    {/* Real-Time Gaze Reading Direction Indicator */}
                    <div className="flex items-center justify-between text-[10px] text-white/90 bg-black/75 px-2.5 py-1 rounded font-sans">
                      <span className="flex items-center gap-1.5 truncate mr-1">
                        {gazeDirectionState === 'down' ? (
                          <span className="text-gyellow font-bold animate-pulse">Glancing Down: Next Line</span>
                        ) : gazeDirectionState === 'up' ? (
                          <span className="text-gblue font-bold animate-pulse">Glancing Up: Prev Line</span>
                        ) : (
                          <span className="text-white/80">Reading Line {activeLineIdx + 1}</span>
                        )}
                      </span>
                      <span className="text-gyellow font-bold font-mono shrink-0">
                        LINE {activeLineIdx + 1} OF {readingLines.length || 1}
                      </span>
                    </div>
                  </div>
                )}

                {!cameraActive && (
                  <div className="p-6 text-center text-white/80 flex flex-col items-center gap-2">
                    <p className="font-bold text-sm text-white">Camera is Off</p>
                    <p className="text-xs text-white/60">Turn on camera to enable real-time eye gaze tracking.</p>
                    <button
                      type="button"
                      className="btn btn-primary btn-sm mt-1 text-white font-bold cursor-pointer"
                      onClick={startCamera}
                    >
                      Start Camera
                    </button>
                  </div>
                )}
              </div>

              {/* Dynamic Calibration & Camera Controls (Clean Balanced Layout - Fits Perfectly In Box) */}
              <div className="mt-3 flex flex-col gap-2">
                {!cameraActive ? (
                  <button
                    type="button"
                    className="btn btn-primary w-full text-sm font-bold text-white cursor-pointer py-2 shadow-xs"
                    onClick={startCamera}
                  >
                    Start Camera
                  </button>
                ) : (
                  <div className="grid grid-cols-2 gap-2 w-full">
                    <button
                      type="button"
                      className="btn btn-primary text-xs font-bold text-white py-2 cursor-pointer w-full text-center shadow-xs"
                      onClick={handleCalibrateGaze}
                      title="Reset gaze tracking baseline to Line 1"
                    >
                      Calibrate Line 1
                    </button>
                    <button
                      type="button"
                      className="btn text-xs font-bold bg-gred text-white border-gred hover:bg-gred/90 py-2 cursor-pointer w-full text-center shadow-xs"
                      onClick={stopCamera}
                      title="Stop camera and tracking"
                    >
                      Stop Camera
                    </button>
                    <button
                      type="button"
                      className={`col-span-2 btn text-xs font-bold py-1.5 px-3 cursor-pointer border w-full text-center ${
                        gazeFollowEnabled
                          ? 'bg-ggreen-light text-ggreen border-ggreen/40 hover:bg-ggreen-light/80'
                          : 'bg-page text-muted border-rule hover:text-ink'
                      }`}
                      onClick={() => setGazeFollowEnabled(!gazeFollowEnabled)}
                      title="Toggle whether eye downward glance advances to next line"
                    >
                      {gazeFollowEnabled ? 'Gaze Follow: ON (Glance down to advance)' : 'Gaze Follow: OFF (Manual reading)'}
                    </button>
                  </div>
                )}

                {cameraActive && (
                  <div className="p-3 rounded-lg bg-page border border-rule flex flex-col gap-2">
                    {/* Manual Step Navigation Buttons */}
                    <div className="flex items-center justify-between gap-2">
                      <button
                        type="button"
                        className="btn btn-sm text-xs flex-1 bg-surface border border-rule hover:bg-white text-ink font-semibold py-1 cursor-pointer"
                        onClick={prevLine}
                        disabled={activeLineIdx <= 0}
                        title="Move to previous line (Up arrow)"
                      >
                        Prev Line
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm text-xs flex-1 bg-surface border border-rule hover:bg-white text-ink font-semibold py-1 cursor-pointer"
                        onClick={nextLine}
                        disabled={activeLineIdx >= readingLines.length - 1}
                        title="Move to next line (Down arrow or Space)"
                      >
                        Next Line
                      </button>
                    </div>

                    <div className="flex items-center justify-between text-xs pt-1 border-t border-rule/50">
                      <span className="font-bold text-ink">Line Reading Status:</span>
                      <span className="font-bold text-gblue">
                        {readingLines.length > 0 ? `Focused on Line ${activeLineIdx + 1}` : 'Ready'}
                      </span>
                    </div>

                    <div className="flex flex-col gap-1.5 text-[11px] text-muted leading-relaxed">
                      <div className="flex items-start gap-1.5">
                        <span className="font-bold text-gblue min-w-[70px]">Eye Gaze:</span>
                        <span>
                          Your eyes are tracked in real-time. When you finish reading a line and glance downward, it advances to the next line.
                        </span>
                      </div>
                      <div className="flex items-start gap-1.5">
                        <span className="font-bold text-ink min-w-[70px]">Keyboard:</span>
                        <span>
                          Use <kbd className="px-1 py-0.2 rounded bg-surface border text-[10px] font-mono font-bold">Down</kbd> or <kbd className="px-1 py-0.2 rounded bg-surface border text-[10px] font-mono font-bold">Space</kbd> to step forward, and <kbd className="px-1 py-0.2 rounded bg-surface border text-[10px] font-mono font-bold">Up</kbd> to step back.
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {cameraError && (
                <p className="text-xs text-gred mt-2 p-2 rounded bg-gred-light font-medium" role="alert">
                  {cameraError}
                </p>
              )}

              <p className="text-xs text-muted mt-2.5">
                Eye tracking runs locally inside your browser to measure where you look.
              </p>

            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          MODE 2: PRINTED BOOKS & WEBCAM (Physical Book Desk Camera)
      ========================================================================= */}
      {settings.mode === 'camera' && (
        <div className="grid gap-6 lg:grid-cols-12 items-start animate-fade-in">
          {/* Main Stage: Physical Book Camera View (8 cols) */}
          <div className="lg:col-span-8 flex flex-col gap-4">
            <div className="google-card p-6">
              {/* Header Banner */}
              <div className="flex flex-wrap items-center justify-between gap-3 pb-4 mb-4 border-b border-rule">
                <div>
                  <h3 className="text-xl font-bold text-ink flex items-center gap-2">
                    <IconEye className="w-5 h-5 text-ggreen" />
                    <span>Printed Books & Worksheets (Desk Camera)</span>
                  </h3>
                  <p className="text-xs text-muted mt-0.5">
                    Point your webcam or document camera at a book or worksheet on your desk.
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  {isCameraRunning ? (
                    <button
                      type="button"
                      className="btn btn-sm px-4 py-1.5 font-bold bg-gred-light text-gred border-gred/40 hover:bg-gred hover:text-white"
                      onClick={() => stop()}
                      disabled={busy}
                    >
                      {busy ? 'Stopping...' : 'Stop Camera'}
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-primary btn-sm px-4 py-1.5 font-bold shadow-xs"
                      onClick={async () => {
                        setSettings({ mode: 'camera' })
                        await post('/api/start', { mode: 'camera', camera: settings.camera, flip_camera: cameraFlipped })
                      }}
                      disabled={busy}
                    >
                      {busy ? 'Starting...' : 'Turn On Book Camera'}
                    </button>
                  )}

                  {/* Mirror / Flip Toggle Button */}
                  <button
                    type="button"
                    className={`btn btn-sm text-xs px-3 py-1.5 border border-rule transition-all ${cameraFlipped ? 'bg-gblue text-white font-bold shadow-xs' : 'bg-page text-ink font-semibold'}`}
                    onClick={handleToggleFlip}
                    title="Flip camera horizontally if your notes appear backwards or mirrored"
                  >
                    <span>{cameraFlipped ? 'Mirror: On (Flipped)' : 'Mirror: Off (Rear)'}</span>
                  </button>

                  <button
                    type="button"
                    className={`btn btn-sm text-xs px-3 py-1.5 border border-rule ${isFrameFrozen ? 'bg-gyellow text-ink font-bold' : 'bg-page text-muted'}`}
                    onClick={() => setIsFrameFrozen(!isFrameFrozen)}
                    title="Freeze frame to read steadily without camera shaking"
                  >
                    {isFrameFrozen ? 'Frame Frozen' : 'Freeze Frame'}
                  </button>
                </div>
              </div>

              {/* Viewport for Printed Book */}
              <div className="aspect-video w-full rounded-2xl overflow-hidden bg-black relative flex items-center justify-center border border-rule shadow-inner">
                {isCameraRunning ? (
                  <>
                    <img
                      src="/api/stream"
                      alt="Printed Book Live Feed"
                      className={`h-full w-full object-contain ${isFrameFrozen ? 'filter brightness-95' : ''}`}
                    />
                    <div className="absolute top-3 left-3 bg-black/75 backdrop-blur-sm px-3 py-1 rounded-full text-xs font-bold text-white flex items-center gap-2 shadow-xs">
                      <span className="flex h-2 w-2 rounded-full bg-ggreen animate-pulse" />
                      <span>{isFrameFrozen ? 'PAGE FROZEN' : (cameraFlipped ? 'LIVE BOOK FEED (MIRRORED)' : 'LIVE BOOK FEED')}</span>
                    </div>

                    <div className="absolute bottom-3 right-3 bg-black/75 backdrop-blur-sm px-3 py-1 rounded-full text-xs font-bold text-white shadow-xs">
                      {cameraWords.length ? `${cameraWords.length} Words Detected` : 'Scanning book page...'}
                    </div>
                  </>
                ) : (
                  <div className="p-8 text-center text-white/90 flex flex-col items-center gap-3">
                    <div className="w-14 h-14 rounded-2xl bg-white/10 flex items-center justify-center text-white">
                      <IconEye className="w-7 h-7" />
                    </div>
                    <div>
                      <h4 className="text-lg font-bold text-white">Aim Webcam at Your Physical Book</h4>
                      <p className="text-xs text-white/70 max-w-sm mt-1">
                        Place your book or worksheet flat under the camera. The assistant reads physical lines in real time.
                      </p>
                    </div>
                    <button
                      type="button"
                      className="btn btn-primary px-5 py-2 text-sm font-bold text-white mt-2 shadow-xs"
                      onClick={async () => {
                        setSettings({ mode: 'camera' })
                        await post('/api/start', { mode: 'camera', camera: settings.camera, flip_camera: cameraFlipped })
                      }}
                      disabled={busy}
                    >
                      {busy ? 'Starting...' : 'Turn On Book Camera'}
                    </button>
                  </div>
                )}
              </div>

              {/* Transcribed Printed Sentences Panel */}
              <div className="mt-5 p-4 rounded-xl bg-page border border-rule">
                <div className="flex flex-wrap items-center justify-between gap-2 pb-3 mb-3 border-b border-rule">
                  <div>
                    <h4 className="font-bold text-ink text-base">Recognized Sentences From Physical Notes / Book</h4>
                    <p className="text-xs text-muted">
                      Continuous sentences from your page. Click the speaker to hear the full sentence or click any word for syllables and pronunciation.
                    </p>
                  </div>
                  <span className={`tag text-xs font-bold ${isCameraRunning ? 'tag-google-green' : 'bg-control text-muted'}`}>
                    {isCameraRunning
                      ? (cameraSentences.length > 0
                          ? `${cameraSentences.length} Sentences (${cameraWords.length} Words)`
                          : cameraWords.length > 0
                            ? `${cameraWords.length} Words Detected`
                            : 'Scanning book / notes...')
                      : 'Camera Off'}
                  </span>
                </div>

                {isCameraRunning && cameraSentences.length > 0 ? (
                  <div className="flex flex-col gap-2.5 max-h-72 overflow-y-auto custom-scrollbar p-1">
                    {cameraSentences.map((st, sIdx) => (
                      <div
                        key={sIdx}
                        className="p-3.5 rounded-xl bg-white border border-rule hover:border-ggreen/60 transition-all flex items-start gap-3 shadow-xs group"
                      >
                        {/* Audio speaker button for the sentence */}
                        <button
                          type="button"
                          className="p-2 rounded-lg bg-ggreen-light/50 text-ggreen hover:bg-ggreen hover:text-white transition-all shrink-0 mt-0.5 cursor-pointer shadow-xs"
                          title="Listen to full sentence spoken aloud"
                          onClick={() => speak(st.text)}
                        >
                          <IconSpeaker className="w-4 h-4" />
                        </button>

                        {/* Sentence words */}
                        <div className="flex-1">
                          <div className="flex flex-wrap gap-1.5 items-center">
                            {st.words.map((w, wIdx) => (
                              <button
                                key={wIdx}
                                type="button"
                                className="px-2 py-0.5 rounded-md text-ink text-sm font-medium hover:bg-ggreen hover:text-white border border-transparent hover:border-ggreen transition-all cursor-pointer"
                                onClick={(e) => showWordMeaning(w.text, e.clientX, e.clientY)}
                                title="Click to view syllables and hear word"
                              >
                                {w.text}
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : isCameraRunning && cameraWords.length > 0 ? (
                  <div className="flex flex-wrap gap-2 max-h-44 overflow-y-auto custom-scrollbar p-1">
                    {cameraWords.map((w, idx) => (
                      <button
                        key={idx}
                        type="button"
                        className="px-2.5 py-1 rounded-lg bg-white border border-rule hover:border-ggreen hover:bg-ggreen-light/30 text-ink text-sm font-medium transition-all shadow-xs cursor-pointer"
                        onClick={(e) => showWordMeaning(w.text, e.clientX, e.clientY)}
                      >
                        {w.text}
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="py-6 text-center text-xs text-muted flex flex-col items-center gap-1.5">
                    <p className="font-semibold text-ink/80">
                      {isCameraRunning
                        ? 'Looking for printed text on your notes...'
                        : 'Camera is currently off.'}
                    </p>
                    <p className="text-[11px] text-muted/80 max-w-md">
                      {isCameraRunning
                        ? 'Hold your notes or book flat in front of the camera with good lighting and keep it steady.'
                        : 'Click "Turn On Book Camera" above to start scanning text and continuous sentences from your physical book or worksheet.'}
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Right Stage: Printed Word Assistance & Reading Tips (4 cols) */}
          <div className="lg:col-span-4 flex flex-col gap-4">
            <div className="google-card p-5">
              <div className="flex items-center justify-between pb-3 mb-3 border-b border-rule">
                <h3 className="font-bold text-ink text-sm">Physical Book Assistant</h3>
                <span className={`tag text-xs font-bold ${isCameraRunning ? 'tag-google-green' : 'bg-control text-muted'}`}>
                  {isCameraRunning ? 'Active Helper' : 'Camera Off'}
                </span>
              </div>

              {isCameraRunning && s.assistance ? (
                <div className="flex flex-col gap-3">
                  <div>
                    <span className="text-[10px] uppercase font-bold text-muted block mb-1">Target Word</span>
                    <h4 className="text-2xl font-extrabold text-ink tracking-tight">{s.assistance.word}</h4>
                  </div>

                  <div className="p-3 rounded-xl bg-page border border-rule">
                    <span className="text-[10px] font-bold uppercase text-muted block mb-1">Syllables:</span>
                    <span className="text-gblue font-bold text-sm">
                      {getSyllables(s.assistance.word).join(' • ')}
                    </span>
                  </div>

                  <p className="text-xs text-ink leading-relaxed font-medium p-3 rounded-xl bg-page border border-rule">
                    {s.assistance.definition}
                  </p>

                  <button
                    type="button"
                    className="btn btn-primary btn-sm text-xs font-bold py-2 mt-1 flex items-center justify-center gap-1.5"
                    onClick={() => {
                      if (s.assistance) speakWord(s.assistance.word, s.assistance.definition)
                    }}
                  >
                    <IconSpeaker className="w-3.5 h-3.5" />
                    <span>Hear Pronunciation</span>
                  </button>
                </div>
              ) : (
                <div className="py-8 text-center text-xs text-muted flex flex-col items-center gap-2">
                  <IconBook className="w-8 h-8 text-muted/60" />
                  <p className="font-semibold text-ink">
                    {isCameraRunning ? 'No Printed Word Targeted' : 'Camera Is Off'}
                  </p>
                  <p className="max-w-xs">
                    {isCameraRunning
                      ? 'Point your camera at a word or click any recognized word to hear pronunciation and syllables.'
                      : 'Turn on the Book Camera to begin live word assistance on your physical notes.'}
                  </p>
                </div>
              )}
            </div>

            {/* Desk Reading Guidance */}
            <div className="p-4 rounded-2xl bg-page border border-rule flex flex-col gap-2.5 text-xs text-muted">
              <h4 className="font-bold text-ink text-xs uppercase tracking-wider">Desk Reading Advice</h4>
              <div className="flex items-start gap-2">
                <IconCheck className="w-4 h-4 text-ggreen shrink-0 mt-0.5" />
                <span>Good room lighting helps text detection on paper.</span>
              </div>
              <div className="flex items-start gap-2">
                <IconCheck className="w-4 h-4 text-ggreen shrink-0 mt-0.5" />
                <span>Angle the camera directly above the book page.</span>
              </div>
              <div className="flex items-start gap-2">
                <IconCheck className="w-4 h-4 text-ggreen shrink-0 mt-0.5" />
                <span>Click &quot;Freeze Frame&quot; if the page moves or shakes.</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          MODE 3: COMPUTER SCREEN (Desktop / Web Page Reading)
      ========================================================================= */}
      {settings.mode === 'screen' && (
        <div className="grid gap-6 lg:grid-cols-12 items-start animate-fade-in">
          {/* Main Stage: Computer Screen Viewport (8 cols) */}
          <div className="lg:col-span-8 flex flex-col gap-4">
            <div className="google-card p-6">
              {/* Header Banner */}
              <div className="flex flex-wrap items-center justify-between gap-3 pb-4 mb-4 border-b border-rule">
                <div>
                  <h3 className="text-xl font-bold text-ink flex items-center gap-2">
                    <IconFile className="w-5 h-5 text-teal" />
                    <span>Computer Screen Reading</span>
                  </h3>
                  <p className="text-xs text-muted mt-0.5">
                    Follow along with articles, websites, and digital reading materials on your screen.
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  {activeScreenRunning ? (
                    <button
                      type="button"
                      className="btn btn-sm px-4 py-1.5 font-bold bg-gred-light text-gred border-gred/40 hover:bg-gred hover:text-white"
                      onClick={stopScreenTracking}
                      disabled={busy}
                    >
                      {busy ? 'Stopping...' : 'Stop Screen Tracking'}
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-primary btn-sm px-4 py-1.5 font-bold shadow-xs"
                      onClick={startScreenTracking}
                      disabled={busy}
                    >
                      {busy ? 'Starting...' : 'Start Screen Tracking'}
                    </button>
                  )}

                  {deviceList.monitors.length > 1 && (
                    <select
                      value={settings.monitor}
                      onChange={(e) => setSettings({ monitor: Number(e.target.value) })}
                      className="text-xs p-1.5 rounded border border-rule bg-page text-ink font-bold cursor-pointer"
                    >
                      {deviceList.monitors.map((m) => (
                        <option key={m.index} value={m.index}>
                          Monitor {m.index}
                        </option>
                      ))}
                    </select>
                  )}

                  <button
                    type="button"
                    className={`btn btn-sm text-xs px-3 py-1.5 border border-rule ${showReadingRuler ? 'bg-gblue-light text-gblue font-bold border-gblue/40' : 'bg-page text-muted'}`}
                    onClick={() => setShowReadingRuler(!showReadingRuler)}
                    title="Toggle horizontal focus reading ruler"
                  >
                    {showReadingRuler ? 'Ruler: On' : 'Ruler: Off'}
                  </button>
                </div>
              </div>

              {/* Viewport for Real Live Screen Capture */}
              <div
                className="aspect-video w-full rounded-2xl overflow-hidden bg-black relative flex items-center justify-center border border-rule shadow-inner select-none"
                onMouseMove={(e) => {
                  const rect = e.currentTarget.getBoundingClientRect()
                  setRulerY(e.clientY - rect.top)
                }}
              >
                {/* Real Live Screen Video Stream */}
                <video
                  ref={screenVideoRef}
                  autoPlay
                  playsInline
                  muted
                  className={`h-full w-full object-contain ${activeScreenRunning && isLocalScreenSharing ? 'block' : 'hidden'}`}
                />

                {activeScreenRunning && !isLocalScreenSharing && (
                  <img
                    src="/api/stream"
                    alt="Screen Capture Stream"
                    className="h-full w-full object-contain"
                  />
                )}

                {activeScreenRunning && (
                  <>
                    {/* Horizontal Reading Ruler Overlay */}
                    {showReadingRuler && (
                      <div
                        className="absolute left-0 right-0 pointer-events-none transition-all duration-75 border-y-2 border-gblue/60 bg-gyellow-light/25 shadow-sm"
                        style={{ top: `${rulerY - 18}px`, height: '36px' }}
                      />
                    )}

                    <div className="absolute top-3 left-3 bg-black/75 backdrop-blur-sm px-3 py-1 rounded-full text-xs font-bold text-white flex items-center gap-2 shadow-xs">
                      <span className="flex h-2 w-2 rounded-full bg-ggreen animate-pulse" />
                      <span>LIVE SCREEN RECORDING</span>
                    </div>

                    <div className="absolute bottom-3 right-3 bg-black/75 backdrop-blur-sm px-3 py-1 rounded-full text-xs font-bold text-white shadow-xs">
                      {screenWords.length ? `${screenWords.length} Screen Words Detected` : 'Tracking desktop text...'}
                    </div>
                  </>
                )}

                {!activeScreenRunning && (
                  <div className="p-8 text-center text-white/90 flex flex-col items-center gap-3">
                    <div className="w-14 h-14 rounded-2xl bg-white/10 flex items-center justify-center text-white">
                      <IconFile className="w-7 h-7" />
                    </div>
                    <div>
                      <h4 className="text-lg font-bold text-white">Live Screen Recording & Assistance</h4>
                      <p className="text-xs text-white/70 max-w-sm mt-1">
                        Select your screen, application window, or document. The assistant captures your real screen in real-time and detects all visible text.
                      </p>
                    </div>
                    {screenSharingError && (
                      <p className="text-xs text-red-300 bg-red-900/40 px-3 py-1 rounded-lg">
                        {screenSharingError}
                      </p>
                    )}
                    <button
                      type="button"
                      className="btn btn-primary px-5 py-2 text-sm font-bold text-white mt-2 shadow-xs"
                      onClick={startScreenTracking}
                      disabled={busy}
                    >
                      {busy ? 'Starting...' : 'Start Screen Tracking'}
                    </button>
                  </div>
                )}
              </div>

              {/* Extracted Screen Sentences & Words Panel */}
              <div className="mt-5 p-5 rounded-2xl bg-page border border-rule">
                <div className="flex items-center justify-between pb-3 mb-3 border-b border-rule">
                  <div>
                    <h4 className="font-bold text-ink text-sm">Recognized Sentences From Screen</h4>
                    <p className="text-xs text-muted">
                      Full sentences and lines transcribed from your shared display. Click speaker to listen, or click any word for syllables.
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {activeScreenRunning && (
                      <button
                        type="button"
                        onClick={() => void captureAndProcessScreenFrame()}
                        disabled={isScanningScreen}
                        className="btn btn-sm text-xs px-3 py-1 bg-white border border-rule hover:border-gblue text-ink font-semibold flex items-center gap-1.5 shadow-xs"
                        title="Re-scan current screen content immediately"
                      >
                        <span className={`w-2 h-2 rounded-full ${isScanningScreen ? 'bg-gyellow animate-ping' : 'bg-ggreen'}`} />
                        <span>{isScanningScreen ? 'Scanning...' : 'Scan Now'}</span>
                      </button>
                    )}
                    <span className={`tag text-xs font-bold ${activeScreenRunning ? 'tag-google-blue' : 'bg-control text-muted'}`}>
                      {activeScreenRunning
                        ? (localScreenSentences.length > 0
                            ? `${localScreenSentences.length} Sentences (${screenWords.length} Words)`
                            : isScanningScreen ? 'Analyzing screen...' : 'No text detected')
                        : 'Screen Off'}
                    </span>
                  </div>
                </div>

                {activeScreenRunning && localScreenSentences.length > 0 ? (
                  <div className="flex flex-col gap-2.5 max-h-72 overflow-y-auto custom-scrollbar p-1">
                    {localScreenSentences.map((st, sIdx) => (
                      <div
                        key={sIdx}
                        className="p-3.5 rounded-xl bg-white border border-rule hover:border-gblue/60 transition-all flex items-start gap-3 shadow-xs group"
                      >
                        {/* Audio speaker button for the sentence */}
                        <button
                          type="button"
                          className="p-2 rounded-lg bg-gblue-light/50 text-gblue hover:bg-gblue hover:text-white transition-all shrink-0 mt-0.5"
                          title="Listen to full sentence spoken aloud"
                          onClick={() => speak(st.text)}
                        >
                          <IconSpeaker className="w-4 h-4" />
                        </button>

                        {/* Sentence words */}
                        <div className="flex-1">
                          <div className="flex flex-wrap gap-1.5 items-center">
                            {st.words.map((w, wIdx) => (
                              <button
                                key={wIdx}
                                type="button"
                                className="px-2 py-0.5 rounded-md text-ink text-sm font-medium hover:bg-gblue hover:text-white border border-transparent hover:border-gblue transition-all cursor-pointer"
                                onClick={(e) => showWordMeaning(w.text, e.clientX, e.clientY)}
                                title="Click to view syllables and hear word"
                              >
                                {w.text}
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="py-8 text-center text-xs text-muted flex flex-col items-center gap-2">
                    {activeScreenRunning ? (
                      <>
                        <div className="w-8 h-8 rounded-full border-2 border-gblue border-t-transparent animate-spin mb-1" />
                        <p className="font-semibold text-ink text-sm">Transcribing text from your shared screen...</p>
                        <p className="max-w-md text-muted text-xs">
                          Switch to any article, PDF, document, or browser tab. Visible sentences and lines will automatically be transcribed and listed down here.
                        </p>
                      </>
                    ) : (
                      'Screen tracking is currently off. Click "Start Screen Tracking" above to begin.'
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Right Stage: Screen Reading Companion (4 cols) */}
          <div className="lg:col-span-4 flex flex-col gap-4">
            <div className="google-card p-5">
              <div className="flex items-center justify-between pb-3 mb-3 border-b border-rule">
                <h3 className="font-bold text-ink text-sm">Screen Companion</h3>
                <span className={`tag text-xs font-bold ${isScreenRunning ? 'tag-google-blue' : 'bg-control text-muted'}`}>
                  {isScreenRunning ? 'Active Helper' : 'Screen Off'}
                </span>
              </div>

              {isScreenRunning && s.assistance ? (
                <div className="flex flex-col gap-3">
                  <div>
                    <span className="text-[10px] uppercase font-bold text-muted block mb-1">Target Word</span>
                    <h4 className="text-2xl font-extrabold text-ink tracking-tight">{s.assistance.word}</h4>
                  </div>

                  <div className="p-3 rounded-xl bg-page border border-rule">
                    <span className="text-[10px] font-bold uppercase text-muted block mb-1">Syllables:</span>
                    <span className="text-gblue font-bold text-sm">
                      {getSyllables(s.assistance.word).join(' • ')}
                    </span>
                  </div>

                  <p className="text-xs text-ink leading-relaxed font-medium p-3 rounded-xl bg-page border border-rule">
                    {s.assistance.definition}
                  </p>

                  <button
                    type="button"
                    className="btn btn-primary btn-sm text-xs font-bold py-2 mt-1 flex items-center justify-center gap-1.5"
                    onClick={() => {
                      if (s.assistance) speakWord(s.assistance.word, s.assistance.definition)
                    }}
                  >
                    <IconSpeaker className="w-3.5 h-3.5" />
                    <span>Hear Pronunciation</span>
                  </button>
                </div>
              ) : (
                <div className="py-8 text-center text-xs text-muted flex flex-col items-center gap-2">
                  <IconFile className="w-8 h-8 text-muted/60" />
                  <p className="font-semibold text-ink">
                    {isScreenRunning ? 'No Word Currently Under Focus' : 'Screen Tracking Is Off'}
                  </p>
                  <p className="max-w-xs">
                    {isScreenRunning
                      ? 'Move your cursor or eyes over words in your browser or document to see instant assistance.'
                      : 'Click "Start Screen Tracking" above to begin live assistance on your screen.'}
                  </p>
                </div>
              )}
            </div>

            {/* Screen Reading Tips */}
            <div className="p-4 rounded-2xl bg-page border border-rule flex flex-col gap-2.5 text-xs text-muted">
              <h4 className="font-bold text-ink text-xs uppercase tracking-wider">Screen Reading Tips</h4>
              <div className="flex items-start gap-2">
                <IconCheck className="w-4 h-4 text-ggreen shrink-0 mt-0.5" />
                <span>Toggle the Reading Ruler to keep focus line-by-line.</span>
              </div>
              <div className="flex items-start gap-2">
                <IconCheck className="w-4 h-4 text-ggreen shrink-0 mt-0.5" />
                <span>Works over any desktop app, web browser, or PDF reader.</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
