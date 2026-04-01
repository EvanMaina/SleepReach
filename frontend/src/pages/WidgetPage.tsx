import { useState } from 'react'
import { Shield, Lock, ChevronRight, ChevronLeft, Check, Phone, Mail, MessageSquare, Heart } from 'lucide-react'

/* ─── Types ─── */
interface WidgetData {
    // Consent
    hipaa_consent: boolean
    communication_consent: boolean
    // Personal
    first_name: string
    last_name: string
    email: string
    phone: string
    date_of_birth: string
    preferred_contact: string
    sms_consent: boolean
    // Assessment
    q3_snore: string
    q4_tired: string
    q5_breathing: string
    q6_sleep_quality: string
    q7_fall_asleep: string
    q8_wake_up: string
    q9_symptoms: string[]
    q10_treatment: string
    // Insurance & Location
    has_insurance: string
    insurance_provider: string
    zip_code: string
    // Referral
    referred: string
    provider_name: string
    provider_specialty: string
    clinic_name: string
    provider_email: string
}

const TOTAL_STEPS = 14

const INITIAL: WidgetData = {
    hipaa_consent: false,
    communication_consent: false,
    first_name: '', last_name: '', email: '', phone: '',
    date_of_birth: '', preferred_contact: '', sms_consent: false,
    q3_snore: '', q4_tired: '', q5_breathing: '',
    q6_sleep_quality: '', q7_fall_asleep: '', q8_wake_up: '',
    q9_symptoms: [], q10_treatment: '',
    has_insurance: '', insurance_provider: '',
    zip_code: '',
    referred: '', provider_name: '', provider_specialty: '',
    clinic_name: '', provider_email: '',
}

/* ─── Phone formatting helper ─── */
function formatPhone(value: string): string {
    const digits = value.replace(/\D/g, '')
    if (digits.length <= 3) return digits
    if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`
    return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6, 10)}`
}

export default function WidgetPage() {
    const [step, setStep] = useState(1)
    const [data, setData] = useState<WidgetData>(INITIAL)
    const [submitting, setSubmitting] = useState(false)
    const [submitted, setSubmitted] = useState(false)
    const [result, setResult] = useState<any>(null)
    const [error, setError] = useState('')
    const apiBase = (window as any).__SLEEPREACH_API_BASE__ || ''
    const logoSrc = apiBase ? `${apiBase}/static/images/sleep-logo.png` : '/images/sleep-logo.png'

    const progress = Math.round((step / TOTAL_STEPS) * 100)

    const set = (field: keyof WidgetData, value: any) =>
        setData(prev => ({ ...prev, [field]: value }))

    const toggleSymptom = (sym: string) => {
        setData(prev => {
            const has = prev.q9_symptoms.includes(sym)
            let next: string[]
            if (sym === 'none') {
                next = has ? [] : ['none']
            } else {
                const without = prev.q9_symptoms.filter(s => s !== 'none')
                next = has ? without.filter(s => s !== sym) : [...without, sym]
            }
            return { ...prev, q9_symptoms: next }
        })
    }

    const isValidEmail = (email: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)

    const canNext = (): boolean => {
        switch (step) {
            case 1: return data.hipaa_consent && data.communication_consent
            case 2: return !!data.first_name.trim() && !!data.last_name.trim()
            case 3: return !!data.email.trim() && isValidEmail(data.email) && !!data.phone.trim() && data.phone.replace(/\D/g, '').length >= 10 && !!data.preferred_contact
            case 4: return !!data.q3_snore
            case 5: return !!data.q4_tired
            case 6: return !!data.q5_breathing
            case 7: return !!data.q6_sleep_quality
            case 8: return !!data.q7_fall_asleep
            case 9: return !!data.q8_wake_up
            case 10: return data.q9_symptoms.length > 0
            case 11: return !!data.q10_treatment
            case 12: return !!data.has_insurance && (data.has_insurance !== 'yes' || !!data.insurance_provider.trim())
            case 13: return !!data.zip_code.trim() && /^\d{5}$/.test(data.zip_code.trim())
            case 14: return !!data.referred
            default: return false
        }
    }

    const handleSubmit = async () => {
        setSubmitting(true)
        setError('')
        try {
            // Score calculations
            const q3Score = data.q3_snore === 'yes' ? 1 : 0
            const q4Score = data.q4_tired === 'yes' ? 1 : 0
            const q5Score = data.q5_breathing === 'yes' ? 1 : 0
            const qualityMap: Record<string, number> = { very_poor: 4, poor: 3, fair: 2, good: 1, very_good: 0 }
            const q6Score = qualityMap[data.q6_sleep_quality] ?? 0
            const fallMap: Record<string, number> = { not_at_all: 0, mildly: 1, moderately: 2, severely: 3, very_severely: 4 }
            const q7Score = fallMap[data.q7_fall_asleep] ?? 0
            const wakeMap: Record<string, number> = { never: 0, rarely: 1, sometimes: 2, often: 3, almost_every_night: 4 }
            const q8Score = wakeMap[data.q8_wake_up] ?? 0

            const apneaSubScore = q3Score + q4Score + q5Score
            const insomniaSubScore = q6Score + q7Score + q8Score
            let otherCondScore = 0
            const detectedConditions: string[] = []

            if (data.q9_symptoms.includes('legs')) { otherCondScore += 2; detectedConditions.push('restless_legs') }
            if (data.q9_symptoms.includes('weakness')) { otherCondScore += 2; detectedConditions.push('narcolepsy') }
            if (data.q9_symptoms.includes('dreams')) { otherCondScore += 2; detectedConditions.push('walking_dreams') }

            const totalScore = apneaSubScore + insomniaSubScore + otherCondScore + q4Score

            // Determine primary condition
            let primaryCondition = 'OTHER'
            if (apneaSubScore > 0 || insomniaSubScore > 0 || detectedConditions.length > 0) {
                const scores = [
                    { name: 'SLEEP_APNEA', score: apneaSubScore },
                    { name: 'INSOMNIA', score: insomniaSubScore },
                ]
                if (detectedConditions.includes('restless_legs')) scores.push({ name: 'RESTLESS_LEG', score: 2 })
                if (detectedConditions.includes('narcolepsy')) scores.push({ name: 'NARCOLEPSY', score: 2 })
                if (detectedConditions.includes('walking_dreams')) scores.push({ name: 'OTHER', score: 2 })
                scores.sort((a, b) => b.score - a.score)
                if (scores[0].score > 0) primaryCondition = scores[0].name
            }

            // Priority
            let priority = 'LOW'
            if (totalScore >= 8 || apneaSubScore === 3 || insomniaSubScore >= 8 || data.q5_breathing === 'yes') {
                priority = 'HOT'
            } else if (totalScore >= 4) {
                priority = 'MEDIUM'
            }

            // Treatment interest mapping
            const treatmentMap: Record<string, string> = {
                cpap: 'cpap_bipap',
                inspire: 'inspire',
                cbti: 'therapy_cbt',
                testing: 'sleep_study',
                not_sure: 'not_sure',
            }

            const payload = {
                first_name: data.first_name.trim(),
                last_name: data.last_name.trim(),
                email: data.email.trim(),
                phone: data.phone.replace(/\D/g, ''),
                date_of_birth: data.date_of_birth || undefined,
                preferred_contact_method: data.preferred_contact || undefined,
                condition: primaryCondition,
                conditions: [primaryCondition, ...detectedConditions.map(c => {
                    if (c === 'restless_legs') return 'RESTLESS_LEG'
                    if (c === 'narcolepsy') return 'NARCOLEPSY'
                    return 'OTHER'
                })].filter((v, i, a) => a.indexOf(v) === i),
                symptom_duration: 'MORE_THAN_12_MONTHS',
                prior_treatments: [],
                has_insurance: data.has_insurance === 'yes',
                insurance_provider: data.has_insurance === 'yes' ? data.insurance_provider.trim() : '',
                zip_code: data.zip_code.trim(),
                urgency: priority === 'HOT' ? 'ASAP' : priority === 'MEDIUM' ? 'WITHIN_30_DAYS' : 'EXPLORING',
                hipaa_consent: data.hipaa_consent,
                sms_consent: data.sms_consent || data.preferred_contact === 'text',
                sleep_treatment_interest: treatmentMap[data.q10_treatment] || 'not_sure',
                is_referral: data.referred === 'yes',
                referring_provider_name: data.referred === 'yes' ? data.provider_name.trim() : '',
                referring_provider_specialty: data.referred === 'yes' ? data.provider_specialty.trim() : '',
                referring_clinic: data.referred === 'yes' ? data.clinic_name.trim() : '',
                referring_provider_email: data.referred === 'yes' ? data.provider_email.trim() : '',
                // Widget assessment scores (sent as metadata)
                widget_scores: {
                    q3_snore: q3Score,
                    q4_tired: q4Score,
                    q5_breathing: q5Score,
                    q6_sleep_quality: q6Score,
                    q7_fall_asleep: q7Score,
                    q8_wake_up: q8Score,
                    q9_symptoms: data.q9_symptoms,
                    apnea_sub_score: apneaSubScore,
                    insomnia_sub_score: insomniaSubScore,
                    other_conditions_score: otherCondScore,
                    total_score: totalScore,
                    priority_calculated: priority,
                },
            }

            const res = await fetch(`${apiBase}/api/leads/submit`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            })

            if (!res.ok) {
                const err = await res.json().catch(() => ({}))
                throw new Error(err.detail || 'Submission failed')
            }

            const json = await res.json()
            setResult(json)
            setSubmitted(true)
        } catch (e: any) {
            setError(e.message || 'Something went wrong. Please try again.')
        } finally {
            setSubmitting(false)
        }
    }

    const next = () => {
        if (step === TOTAL_STEPS) { handleSubmit(); return }
        setStep(s => Math.min(s + 1, TOTAL_STEPS))
    }
    const prev = () => setStep(s => Math.max(s - 1, 1))

    // ── Styles ──
    const btnPrimary = 'w-full py-3.5 rounded-xl font-semibold text-white text-[15px] transition-all duration-200 flex items-center justify-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed'
    const btnStyle = { background: 'linear-gradient(135deg, #243448 0%, #2C3E5A 50%, #3B5068 100%)' }
    const radioBtn = (selected: boolean) =>
        `w-full p-3.5 rounded-xl border-2 text-left text-sm font-medium transition-all cursor-pointer ${selected ? 'border-[#2C3E5A] bg-[#2C3E5A]/5 text-[#1E2D3D]' : 'border-gray-200 hover:border-gray-300 text-gray-600'}`
    const checkBtn = (selected: boolean) =>
        `w-full p-3.5 rounded-xl border-2 text-left text-sm font-medium transition-all cursor-pointer ${selected ? 'border-[#2C3E5A] bg-[#2C3E5A]/5 text-[#1E2D3D]' : 'border-gray-200 hover:border-gray-300 text-gray-600'}`
    const inputCls = 'w-full px-4 py-3 rounded-xl border border-gray-200 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-[#2C3E5A]/30 focus:border-[#2C3E5A] transition-all'

    // Preferred contact card style
    const contactCard = (selected: boolean) =>
        `flex flex-col items-center justify-center gap-1.5 p-3 rounded-xl border-2 cursor-pointer transition-all ${selected ? 'border-[#2C3E5A] bg-[#2C3E5A]/5 text-[#1E2D3D]' : 'border-gray-200 hover:border-gray-300 text-gray-500'}`

    if (submitted) {
        return (
            <div className="sr-widget-page min-h-screen bg-gray-50 flex items-center justify-center p-4">
                <div className="sr-widget-card w-full max-w-md bg-white rounded-2xl shadow-xl overflow-hidden">
                    <div className="sr-widget-header p-6 text-center" style={{ background: 'linear-gradient(135deg, #243448 0%, #2C3E5A 50%, #3B5068 100%)' }}>
                        <img src={logoSrc} alt="The Insomnia and Sleep Institute of Arizona" className="sr-widget-logo mx-auto mb-3" style={{ filter: 'brightness(0) invert(1)' }} />
                        <h2 className="text-xl font-bold text-white">Thank You!</h2>
                    </div>
                    <div className="p-8 text-center">
                        <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-4">
                            <Check className="w-8 h-8 text-green-600" />
                        </div>
                        <h3 className="text-lg font-bold text-gray-900 mb-2">Assessment Complete</h3>
                        <p className="text-sm text-gray-500 mb-4">
                            {result?.message || 'A care coordinator will contact you shortly.'}
                        </p>
                        <div className="bg-gray-50 rounded-xl p-4 text-left text-sm space-y-2">
                            <div className="flex justify-between"><span className="text-gray-500">Priority</span><span className="font-semibold text-gray-900">{result?.priority || '—'}</span></div>
                            <div className="flex justify-between"><span className="text-gray-500">Response Time</span><span className="font-semibold text-gray-900">{result?.estimated_response_time || '—'}</span></div>
                        </div>
                        <p className="sr-widget-trust-row mt-6 text-xs text-gray-400 flex items-center justify-center">
                            <Lock className="w-3 h-3" /> 256-bit encryption • HIPAA compliant
                        </p>
                        <p className="sr-widget-footer-note mt-2 text-[10px] text-gray-300">© 2026 The Insomnia and Sleep Institute of Arizona. All rights reserved.</p>
                    </div>
                </div>
            </div>
        )
    }

    return (
        <div className="sr-widget-page sr-widget-modal-context min-h-screen bg-gray-50 flex items-center justify-center p-4">
            <div className="sr-widget-card w-full max-w-md bg-white rounded-2xl shadow-xl overflow-hidden">
                {/* Header */}
                <div className="sr-widget-header p-5 text-center" style={{ background: 'linear-gradient(135deg, #243448 0%, #2C3E5A 50%, #3B5068 100%)' }}>
                    <img src={logoSrc} alt="The Insomnia and Sleep Institute of Arizona" className="sr-widget-logo mx-auto mb-3" style={{ filter: 'brightness(0) invert(1)' }} />
                    <h1 className="sr-widget-title text-lg font-bold text-white">The Insomnia and Sleep Institute of Arizona</h1>
                    <p className="text-white/70 text-sm">Free Sleep Assessment</p>
                    <p className="text-white/50 text-xs mt-1">About 2 minutes • Confidential</p>
                </div>

                {/* Progress Bar */}
                <div className="px-6 pt-4">
                    <div className="flex items-center justify-between mb-1.5">
                        <span className="text-xs font-medium text-gray-500">Step {step} of {TOTAL_STEPS}</span>
                        <span className="text-xs font-semibold text-[#2C3E5A]">{progress}%</span>
                    </div>
                    <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
                        <div className="h-full rounded-full transition-all duration-500 ease-out" style={{ width: `${progress}%`, background: 'linear-gradient(90deg, #2C3E5A, #3B5068)' }} />
                    </div>
                </div>

                {/* Step Content */}
                <div className="sr-widget-step p-6 min-h-[320px] flex flex-col">
                    <div className="flex-1">
                        {/* ═══ Step 1: Consent ═══ */}
                        {step === 1 && (
                            <div className="space-y-4">
                                <h2 className="text-lg font-bold text-gray-900">Welcome to Your Sleep Assessment</h2>
                                <p className="sr-widget-note text-sm text-gray-500">Before we begin, please review our privacy practices and confirm that we may contact you about your sleep consultation.</p>

                                {/* HIPAA Privacy Notice */}
                                <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
                                    <div className="flex items-start gap-2.5 mb-2">
                                        <Shield className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
                                        <div>
                                            <p className="text-sm font-semibold text-blue-900">HIPAA Privacy Notice</p>
                                            <p className="text-xs text-blue-700 mt-1 leading-relaxed">
                                                Your health information is protected under the Health Insurance Portability and Accountability Act (HIPAA).
                                                We use industry-standard encryption and security measures to protect your data.
                                                Your information will only be used to assess your sleep health needs and connect you with appropriate care.
                                            </p>
                                        </div>
                                    </div>
                                </div>

                                {/* Consent checkboxes */}
                                <button
                                    className={checkBtn(data.hipaa_consent)}
                                    onClick={() => set('hipaa_consent', !data.hipaa_consent)}
                                >
                                    <div className="flex items-start gap-3">
                                        <div className={`w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 mt-0.5 ${data.hipaa_consent ? 'border-[#2C3E5A] bg-[#2C3E5A]' : 'border-gray-300'}`}>
                                            {data.hipaa_consent && <Check className="w-3 h-3 text-white" />}
                                        </div>
                                        <span className="text-sm leading-relaxed">I acknowledge that my health information will be collected and used in accordance with HIPAA privacy practices.</span>
                                    </div>
                                </button>

                                <button
                                    className={checkBtn(data.communication_consent)}
                                    onClick={() => set('communication_consent', !data.communication_consent)}
                                >
                                    <div className="flex items-start gap-3">
                                        <div className={`w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 mt-0.5 ${data.communication_consent ? 'border-[#2C3E5A] bg-[#2C3E5A]' : 'border-gray-300'}`}>
                                            {data.communication_consent && <Check className="w-3 h-3 text-white" />}
                                        </div>
                                        <span className="text-sm leading-relaxed">I consent to be contacted by the care team regarding my assessment results via phone, email, or text message.</span>
                                    </div>
                                </button>
                            </div>
                        )}

                        {/* ═══ Step 2: Personal Info ═══ */}
                        {step === 2 && (
                            <div className="space-y-4">
                                <h2 className="text-lg font-bold text-gray-900">Personal Information</h2>
                                <p className="text-sm text-gray-500">Let's start with your name.</p>
                                <input className={inputCls} placeholder="First Name *" value={data.first_name} onChange={e => set('first_name', e.target.value)} />
                                <input className={inputCls} placeholder="Last Name *" value={data.last_name} onChange={e => set('last_name', e.target.value)} />
                            </div>
                        )}

                        {/* ═══ Step 3: Contact + Preferred Contact + DOB ═══ */}
                        {step === 3 && (
                            <div className="space-y-4">
                                <h2 className="text-lg font-bold text-gray-900">Contact Information</h2>
                                <p className="text-sm text-gray-500">How can we reach you?</p>
                                <input className={inputCls} type="email" placeholder="Email *" value={data.email} onChange={e => set('email', e.target.value)} />
                                <input
                                    className={inputCls}
                                    type="tel"
                                    placeholder="Phone * (e.g. 602-555-1234)"
                                    value={data.phone}
                                    onChange={e => set('phone', formatPhone(e.target.value))}
                                    maxLength={14}
                                />

                                {/* Date of Birth (optional) */}
                                <div>
                                    <label className="text-xs font-medium text-gray-500 mb-1 block">Date of Birth <span className="text-gray-400">(optional)</span></label>
                                    <input className={inputCls} type="date" value={data.date_of_birth} onChange={e => set('date_of_birth', e.target.value)} />
                                </div>

                                {/* Preferred Contact Method */}
                                <div>
                                    <label className="text-xs font-medium text-gray-500 mb-2 block">Preferred Contact Method *</label>
                                    <div className="grid grid-cols-2 gap-2">
                                        {[
                                            { value: 'phone', label: 'Phone', icon: Phone },
                                            { value: 'text', label: 'Text', icon: MessageSquare },
                                            { value: 'email', label: 'Email', icon: Mail },
                                            { value: 'any', label: 'Any', icon: Heart },
                                        ].map(opt => (
                                            <button
                                                key={opt.value}
                                                className={contactCard(data.preferred_contact === opt.value)}
                                                onClick={() => set('preferred_contact', opt.value)}
                                            >
                                                <opt.icon className="w-[18px] h-[18px]" />
                                                <span className="text-xs font-semibold">{opt.label}</span>
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                {/* SMS consent (shown if text selected) */}
                                {(data.preferred_contact === 'text' || data.preferred_contact === 'any') && (
                                    <button
                                        className={`w-full p-3 rounded-xl border text-left text-xs transition-all cursor-pointer ${data.sms_consent ? 'border-[#2C3E5A] bg-[#2C3E5A]/5' : 'border-gray-200'}`}
                                        onClick={() => set('sms_consent', !data.sms_consent)}
                                    >
                                        <div className="flex items-start gap-2.5">
                                            <div className={`w-4 h-4 rounded border-2 flex items-center justify-center flex-shrink-0 mt-0.5 ${data.sms_consent ? 'border-[#2C3E5A] bg-[#2C3E5A]' : 'border-gray-300'}`}>
                                                {data.sms_consent && <Check className="w-2.5 h-2.5 text-white" />}
                                            </div>
                                            <span className="text-gray-600 leading-relaxed">I agree to receive SMS messages. Message & data rates may apply. Reply STOP to opt out.</span>
                                        </div>
                                    </button>
                                )}
                            </div>
                        )}

                        {/* ═══ Step 4: Snoring ═══ */}
                        {step === 4 && (
                            <div className="space-y-3">
                                <h2 className="text-lg font-bold text-gray-900">Do you snore loudly?</h2>
                                <p className="text-sm text-gray-500">Louder than talking or heard through closed doors</p>
                                {['yes', 'no'].map(v => (
                                    <button key={v} className={radioBtn(data.q3_snore === v)} onClick={() => set('q3_snore', v)}>
                                        {v === 'yes' ? 'Yes' : 'No'}
                                    </button>
                                ))}
                            </div>
                        )}

                        {/* ═══ Step 5: Tired ═══ */}
                        {step === 5 && (
                            <div className="space-y-3">
                                <h2 className="text-lg font-bold text-gray-900">Do you often feel tired, fatigued, or sleepy during the daytime?</h2>
                                {['yes', 'no'].map(v => (
                                    <button key={v} className={radioBtn(data.q4_tired === v)} onClick={() => set('q4_tired', v)}>
                                        {v === 'yes' ? 'Yes' : 'No'}
                                    </button>
                                ))}
                            </div>
                        )}

                        {/* ═══ Step 6: Breathing ═══ */}
                        {step === 6 && (
                            <div className="space-y-3">
                                <h2 className="text-lg font-bold text-gray-900">Has anyone observed you stop breathing or choking/gasping during sleep?</h2>
                                {['yes', 'no'].map(v => (
                                    <button key={v} className={radioBtn(data.q5_breathing === v)} onClick={() => set('q5_breathing', v)}>
                                        {v === 'yes' ? 'Yes' : 'No'}
                                    </button>
                                ))}
                            </div>
                        )}

                        {/* ═══ Step 7: Sleep Quality ═══ */}
                        {step === 7 && (
                            <div className="space-y-3">
                                <h2 className="text-lg font-bold text-gray-900">How would you rate your current sleep quality?</h2>
                                {[
                                    { v: 'very_poor', l: 'Very poor' },
                                    { v: 'poor', l: 'Poor' },
                                    { v: 'fair', l: 'Fair' },
                                    { v: 'good', l: 'Good' },
                                    { v: 'very_good', l: 'Very good' },
                                ].map(o => (
                                    <button key={o.v} className={radioBtn(data.q6_sleep_quality === o.v)} onClick={() => set('q6_sleep_quality', o.v)}>
                                        {o.l}
                                    </button>
                                ))}
                            </div>
                        )}

                        {/* ═══ Step 8: Fall Asleep ═══ */}
                        {step === 8 && (
                            <div className="space-y-3">
                                <h2 className="text-lg font-bold text-gray-900">How difficult is it for you to fall asleep at night?</h2>
                                {[
                                    { v: 'not_at_all', l: 'Not at all' },
                                    { v: 'mildly', l: 'Mildly' },
                                    { v: 'moderately', l: 'Moderately' },
                                    { v: 'severely', l: 'Severely' },
                                    { v: 'very_severely', l: 'Very severely' },
                                ].map(o => (
                                    <button key={o.v} className={radioBtn(data.q7_fall_asleep === o.v)} onClick={() => set('q7_fall_asleep', o.v)}>
                                        {o.l}
                                    </button>
                                ))}
                            </div>
                        )}

                        {/* ═══ Step 9: Wake Up ═══ */}
                        {step === 9 && (
                            <div className="space-y-3">
                                <h2 className="text-lg font-bold text-gray-900">How often do you wake up during the night or too early?</h2>
                                {[
                                    { v: 'never', l: 'Never' },
                                    { v: 'rarely', l: 'Rarely' },
                                    { v: 'sometimes', l: 'Sometimes' },
                                    { v: 'often', l: 'Often' },
                                    { v: 'almost_every_night', l: 'Almost every night' },
                                ].map(o => (
                                    <button key={o.v} className={radioBtn(data.q8_wake_up === o.v)} onClick={() => set('q8_wake_up', o.v)}>
                                        {o.l}
                                    </button>
                                ))}
                            </div>
                        )}

                        {/* ═══ Step 10: Symptoms ═══ */}
                        {step === 10 && (
                            <div className="space-y-3">
                                <h2 className="text-lg font-bold text-gray-900">Do you experience any of the following?</h2>
                                <p className="text-sm text-gray-500">Select all that apply</p>
                                {[
                                    { v: 'legs', l: 'Uncomfortable urge to move your legs at rest' },
                                    { v: 'weakness', l: 'Sudden muscle weakness triggered by emotions' },
                                    { v: 'dreams', l: 'Walking or acting out dreams during sleep' },
                                    { v: 'none', l: 'None of the above' },
                                ].map(o => (
                                    <button key={o.v} className={checkBtn(data.q9_symptoms.includes(o.v))} onClick={() => toggleSymptom(o.v)}>
                                        <div className="flex items-center gap-3">
                                            <div className={`w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 ${data.q9_symptoms.includes(o.v) ? 'border-[#2C3E5A] bg-[#2C3E5A]' : 'border-gray-300'}`}>
                                                {data.q9_symptoms.includes(o.v) && <Check className="w-3 h-3 text-white" />}
                                            </div>
                                            {o.l}
                                        </div>
                                    </button>
                                ))}
                            </div>
                        )}

                        {/* ═══ Step 11: Treatment Interest ═══ */}
                        {step === 11 && (
                            <div className="space-y-3">
                                <h2 className="text-lg font-bold text-gray-900">What treatment are you most interested in?</h2>
                                {[
                                    { v: 'cpap', l: 'CPAP Therapy' },
                                    { v: 'inspire', l: 'Inspire Therapy' },
                                    { v: 'cbti', l: 'CBT-I (Cognitive Behavioral Therapy for Insomnia)' },
                                    { v: 'testing', l: 'Getting a sleep study / diagnostic testing' },
                                    { v: 'not_sure', l: "Not sure — I'd like to learn more" },
                                ].map(o => (
                                    <button key={o.v} className={radioBtn(data.q10_treatment === o.v)} onClick={() => set('q10_treatment', o.v)}>
                                        {o.l}
                                    </button>
                                ))}
                            </div>
                        )}

                        {/* ═══ Step 12: Insurance ═══ */}
                        {step === 12 && (
                            <div className="space-y-3">
                                <h2 className="text-lg font-bold text-gray-900">Do you have insurance?</h2>
                                {['yes', 'no', 'not_sure'].map(v => (
                                    <button key={v} className={radioBtn(data.has_insurance === v)} onClick={() => set('has_insurance', v)}>
                                        {v === 'yes' ? 'Yes' : v === 'no' ? 'No' : 'Not Sure'}
                                    </button>
                                ))}
                                {data.has_insurance === 'yes' && (
                                    <input className={inputCls} placeholder="Insurance Provider *" value={data.insurance_provider} onChange={e => set('insurance_provider', e.target.value)} />
                                )}
                            </div>
                        )}

                        {/* ═══ Step 13: Location ═══ */}
                        {step === 13 && (
                            <div className="space-y-4">
                                <h2 className="text-lg font-bold text-gray-900">What is your ZIP code?</h2>
                                <p className="text-sm text-gray-500">This helps us determine if we serve your area.</p>
                                <input className={inputCls} placeholder="ZIP Code (5 digits) *" maxLength={5} value={data.zip_code} onChange={e => set('zip_code', e.target.value.replace(/\D/g, ''))} />
                            </div>
                        )}

                        {/* ═══ Step 14: Referral (with full fields) ═══ */}
                        {step === 14 && (
                            <div className="space-y-3">
                                <h2 className="text-lg font-bold text-gray-900">Were you referred by a provider?</h2>
                                {['yes', 'no'].map(v => (
                                    <button key={v} className={radioBtn(data.referred === v)} onClick={() => set('referred', v)}>
                                        {v === 'yes' ? 'Yes' : 'No'}
                                    </button>
                                ))}
                                {data.referred === 'yes' && (
                                    <div className="space-y-3 mt-2">
                                        <input
                                            className={inputCls}
                                            placeholder="Provider Name"
                                            value={data.provider_name}
                                            onChange={e => set('provider_name', e.target.value)}
                                        />
                                        <input
                                            className={inputCls}
                                            placeholder="Provider Specialty"
                                            value={data.provider_specialty}
                                            onChange={e => set('provider_specialty', e.target.value)}
                                        />
                                        <input
                                            className={inputCls}
                                            placeholder="Clinic or Practice Name"
                                            value={data.clinic_name}
                                            onChange={e => set('clinic_name', e.target.value)}
                                        />
                                        <input
                                            className={inputCls}
                                            type="email"
                                            placeholder="Provider Email"
                                            value={data.provider_email}
                                            onChange={e => set('provider_email', e.target.value)}
                                        />
                                        <p className="text-xs text-gray-500 leading-relaxed">
                                            If you were referred, adding the provider details helps us tag the referral correctly and keep the referring clinic updated.
                                        </p>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Error */}
                    {error && (
                        <div className="mt-3 p-3 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">{error}</div>
                    )}

                    {/* Navigation */}
                    <div className="mt-6 space-y-3">
                        <button className={btnPrimary} style={btnStyle} disabled={!canNext() || submitting} onClick={next}>
                            {submitting ? (
                                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                            ) : step === TOTAL_STEPS ? (
                                <>Submit Assessment <Check className="w-4 h-4" /></>
                            ) : (
                                <>Continue <ChevronRight className="w-4 h-4" /></>
                            )}
                        </button>
                        {step > 1 && (
                            <button className="w-full py-2.5 rounded-xl text-sm font-medium text-gray-500 hover:text-gray-700 flex items-center justify-center gap-1 transition-colors" onClick={prev}>
                                <ChevronLeft className="w-4 h-4" /> Back
                            </button>
                        )}
                    </div>
                </div>

                {/* Footer */}
                <div className="px-6 pb-5 text-center">
                    <p className="sr-widget-trust-row text-xs text-gray-400 flex items-center justify-center">
                        <Shield className="w-3 h-3" /> 256-bit encryption • HIPAA compliant
                    </p>
                    <p className="sr-widget-footer-note mt-1.5 text-[10px] text-gray-300">© 2026 The Insomnia and Sleep Institute of Arizona. All rights reserved.</p>
                </div>
            </div>
        </div>
    )
}
