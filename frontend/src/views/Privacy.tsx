import { IconShield, IconEye, IconBook, IconLock, IconCheck } from './shared'

export default function Privacy() {
  return (
    <div className="flex flex-col gap-8 animate-fade-in">
      <div>
        <h2 className="text-3xl font-extrabold text-ink tracking-tight">Privacy & Safety</h2>
        <p className="text-muted text-sm mt-0.5">
          Your reading material, camera, and eyes stay completely private on your device.
        </p>
      </div>

      {/* Hero Privacy Promise */}
      <section className="card-panel border-t-4 border-t-ggreen">
        <div className="flex items-start gap-4">
          <div className="p-3 rounded-2xl bg-ggreen-light flex-none flex items-center justify-center">
            <IconShield className="w-8 h-8 text-ggreen" />
          </div>
          <div>
            <h3 className="text-xl font-bold text-ink">100% Private on Your Device</h3>
            <p className="text-ink leading-relaxed mt-1.5">
              Your reading companion is built from the ground up to protect your privacy. 
              Your camera view, documents, and reading habits <strong>never leave your computer</strong>. 
              Everything happens right here on your screen, with no tracking and no personal data stored.
            </p>
          </div>
        </div>
      </section>

      {/* 4 Core Privacy Guarantees */}
      <section aria-labelledby="h-pillars" className="grid gap-5 md:grid-cols-2">
        <h3 id="h-pillars" className="sr-only">Privacy Guarantees</h3>

        {/* Pillar 1: Camera & Eye Tracking */}
        <div className="card-panel flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2.5 mb-2">
              <IconEye className="w-5 h-5 text-teal" />
              <h4 className="text-lg font-bold text-ink">Camera & Eye Tracking Safety</h4>
            </div>
            <p className="text-sm text-muted leading-relaxed">
              When eye tracking is turned on, camera pictures are processed in temporary memory for a fraction of a second to follow your gaze and immediately discarded. 
              <strong>No video or photos are ever saved or uploaded anywhere.</strong>
            </p>
          </div>
          <span className="tag tag-google-green text-xs font-bold mt-4 self-start">
            Processed in-memory only
          </span>
        </div>

        {/* Pillar 2: Reading Material & Documents */}
        <div className="card-panel flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2.5 mb-2">
              <IconBook className="w-5 h-5 text-gblue" />
              <h4 className="text-lg font-bold text-ink">Your Documents Stay Private</h4>
            </div>
            <p className="text-sm text-muted leading-relaxed">
              Whether you read a school book, a PDF article, or personal notes, your full document stays strictly on your computer. 
              Only the single word you pause on for help is looked up to give you its simple definition.
            </p>
          </div>
          <span className="tag tag-google-green text-xs font-bold mt-4 self-start">
            Never uploaded or shared
          </span>
        </div>

        {/* Pillar 3: No Personal Data or Accounts */}
        <div className="card-panel flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2.5 mb-2">
              <IconLock className="w-5 h-5 text-muted" />
              <h4 className="text-lg font-bold text-ink">Zero Personal Data Collection</h4>
            </div>
            <p className="text-sm text-muted leading-relaxed">
              We do not ask for your name, email, or passwords. There are no advertising trackers, no cookies profiling your reading, and no third-party analytics.
            </p>
          </div>
          <span className="tag tag-google-green text-xs font-bold mt-4 self-start">
            No accounts or tracking
          </span>
        </div>

        {/* Pillar 4: Child & Student Safe */}
        <div className="card-panel flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2.5 mb-2">
              <IconShield className="w-5 h-5 text-ggreen" />
              <h4 className="text-lg font-bold text-ink">Safe for Students & Young Learners</h4>
            </div>
            <p className="text-sm text-muted leading-relaxed">
              Designed specifically with young dyslexic learners and schools in mind. All speech audio is synthesized naturally on your computer to provide a safe, distraction-free environment.
            </p>
          </div>
          <span className="tag tag-google-green text-xs font-bold mt-4 self-start">
            Child-friendly & safe
          </span>
        </div>
      </section>

      {/* Safety Summary Checklist */}
      <section className="card-panel bg-page border-rule/80">
        <h3 className="text-lg font-bold text-ink mb-3">Privacy Standards Summary</h3>
        <ul className="grid gap-2.5 sm:grid-cols-2 list-none p-0 text-sm">
          <li className="flex items-center gap-2.5 text-ink font-medium">
            <IconCheck className="w-4 h-4 text-ggreen flex-none" />
            <span>Webcam video is never recorded or stored</span>
          </li>
          <li className="flex items-center gap-2.5 text-ink font-medium">
            <IconCheck className="w-4 h-4 text-ggreen flex-none" />
            <span>Full books and documents never leave your computer</span>
          </li>
          <li className="flex items-center gap-2.5 text-ink font-medium">
            <IconCheck className="w-4 h-4 text-ggreen flex-none" />
            <span>No advertising cookies or user profiling</span>
          </li>
          <li className="flex items-center gap-2.5 text-ink font-medium">
            <IconCheck className="w-4 h-4 text-ggreen flex-none" />
            <span>Works smoothly with built-in private speech</span>
          </li>
        </ul>
      </section>
    </div>
  )
}
