import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
    Check,
    ChevronLeft,
    ChevronRight,
    Lock,
    Shield,
} from 'lucide-react'

type ConditionType = 'INSOMNIA' | 'SLEEP_APNEA' | 'RESTLESS_LEG' | 'NARCOLEPSY' | 'OTHER'
type DurationType = 'LESS_THAN_6_MONTHS' | 'SIX_TO_TWELVE_MONTHS' | 'MORE_THAN_12_MONTHS'
type TreatmentType = 'CPAP_BIPAP' | 'MEDICATION' | 'SLEEP_STUDY' | 'THERAPY_CBT' | 'NONE' | 'OTHER'
type UrgencyType = 'ASAP' | 'WITHIN_30_DAYS' | 'EXPLORING'
type PreferredContactMethod = 'phone_call' | 'text' | 'email' | 'any'
type SleepTreatmentInterest = 'cpap_bipap' | 'inspire' | 'therapy_cbt' | 'sleep_study' | 'medication' | 'not_sure'

interface AssessmentPageProps {
    apiUrl: string
}

interface AssessmentFormData {
    hipaaConsent: boolean
    conditions: ConditionType[]
    conditionOther: string
    sleepTreatmentInterest: SleepTreatmentInterest | null
    symptomDuration: DurationType | null
    priorTreatments: TreatmentType[]
    urgency: UrgencyType | null
    isReferral: boolean | null
    referringProviderName: string
    referringProviderSpecialty: string
    referringClinic: string
    referringProviderEmail: string
    firstName: string
    lastName: string
    email: string
    phone: string
    dateOfBirth: string
    preferredContactMethod: PreferredContactMethod | null
    smsConsent: boolean
    hasInsurance: boolean | null
    insuranceProvider: string
    zipCode: string
}

interface LeadSubmitResponse {
    success: boolean
    message: string
    lead_id?: string
    lead_number?: string
    priority?: string
    estimated_response_time?: string
}

interface UTMParams {
    utm_source?: string
    utm_medium?: string
    utm_campaign?: string
    utm_term?: string
    utm_content?: string
}

const TOTAL_INPUT_STEPS = 10

const STEP_NAMES = [
    'Consent',
    'Condition',
    'Interest',
    'Duration',
    'Treatment',
    'Urgency',
    'Referral',
    'Contact',
    'Communication',
    'Final details',
] as const

const INITIAL_FORM: AssessmentFormData = {
    hipaaConsent: false,
    conditions: [],
    conditionOther: '',
    sleepTreatmentInterest: null,
    symptomDuration: null,
    priorTreatments: [],
    urgency: null,
    isReferral: null,
    referringProviderName: '',
    referringProviderSpecialty: '',
    referringClinic: '',
    referringProviderEmail: '',
    firstName: '',
    lastName: '',
    email: '',
    phone: '',
    dateOfBirth: '',
    preferredContactMethod: null,
    smsConsent: false,
    hasInsurance: null,
    insuranceProvider: '',
    zipCode: '',
}

const CONDITION_OPTIONS: Array<{ value: ConditionType; label: string; description: string }> = [
    { value: 'INSOMNIA', label: 'Insomnia', description: 'Trouble falling asleep, staying asleep, or waking too early.' },
    { value: 'SLEEP_APNEA', label: 'Sleep Apnea', description: 'Snoring, gasping, breathing pauses, or non-restorative sleep.' },
    { value: 'RESTLESS_LEG', label: 'Restless Legs', description: 'An urge to move your legs that disrupts evening rest.' },
    { value: 'NARCOLEPSY', label: 'Narcolepsy', description: 'Excessive daytime sleepiness or sudden sleep attacks.' },
    { value: 'OTHER', label: 'Other Sleep Concern', description: 'Another sleep issue you would like to discuss with the clinic.' },
]

const INTEREST_OPTIONS: Array<{ value: SleepTreatmentInterest; label: string; description: string }> = [
    { value: 'cpap_bipap', label: 'CPAP or BiPAP', description: 'Support with PAP therapy for sleep apnea or breathing-related sleep issues.' },
    { value: 'inspire', label: 'Inspire Therapy', description: 'Learn whether Inspire may be a fit for your sleep apnea treatment plan.' },
    { value: 'therapy_cbt', label: 'CBT-I Therapy', description: 'A non-medication approach for chronic insomnia and sleep habits.' },
    { value: 'sleep_study', label: 'Sleep Study', description: 'Diagnostic testing to understand what is affecting your sleep.' },
    { value: 'medication', label: 'Medication Review', description: 'Discuss sleep-supporting medication options with a specialist.' },
    { value: 'not_sure', label: 'Not Sure Yet', description: 'You want guidance on the best next step for your sleep concerns.' },
]

const DURATION_OPTIONS: Array<{ value: DurationType; label: string; description: string }> = [
    { value: 'LESS_THAN_6_MONTHS', label: 'Less than 6 months', description: 'This sleep issue started relatively recently.' },
    { value: 'SIX_TO_TWELVE_MONTHS', label: '6 to 12 months', description: 'Symptoms have been affecting your routine for several months.' },
    { value: 'MORE_THAN_12_MONTHS', label: 'More than 12 months', description: 'This has been an ongoing issue for at least a year.' },
]

const TREATMENT_OPTIONS: Array<{ value: TreatmentType; label: string; description: string }> = [
    { value: 'CPAP_BIPAP', label: 'CPAP or BiPAP', description: 'You have used PAP therapy before.' },
    { value: 'MEDICATION', label: 'Medication', description: 'You have tried prescription or over-the-counter sleep medication.' },
    { value: 'SLEEP_STUDY', label: 'Sleep Study', description: 'You have completed a sleep study before.' },
    { value: 'THERAPY_CBT', label: 'Therapy or CBT-I', description: 'You have tried therapy, coaching, or CBT-I support.' },
    { value: 'NONE', label: 'No prior treatment', description: 'You are just getting started.' },
    { value: 'OTHER', label: 'Other', description: 'You have tried another sleep-related intervention.' },
]

const URGENCY_OPTIONS: Array<{ value: UrgencyType; label: string; description: string }> = [
    { value: 'ASAP', label: 'As soon as possible', description: 'Sleep symptoms are impacting your health or daily functioning now.' },
    { value: 'WITHIN_30_DAYS', label: 'Within 30 days', description: 'You would like to speak with the clinic soon.' },
    { value: 'EXPLORING', label: 'Just exploring', description: 'You are still learning about options and timing.' },
]

const CONTACT_METHOD_OPTIONS: Array<{ value: PreferredContactMethod; label: string }> = [
    { value: 'phone_call', label: 'Phone' },
    { value: 'text', label: 'Text' },
    { value: 'email', label: 'Email' },
    { value: 'any', label: 'Any' },
]

function generateSubmissionId(): string {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
        return crypto.randomUUID()
    }

    const rand = Array.from({ length: 16 }, () => Math.floor(Math.random() * 16).toString(16)).join('')
    return `sleep-widget-${Date.now()}-${rand}`
}

function getMarketingAttribution(): { utm_params?: UTMParams; referrer_url?: string } {
    const search = new URLSearchParams(window.location.search)
    const utmParams: UTMParams = {
        utm_source: search.get('utm_source') || undefined,
        utm_medium: search.get('utm_medium') || undefined,
        utm_campaign: search.get('utm_campaign') || undefined,
        utm_term: search.get('utm_term') || undefined,
        utm_content: search.get('utm_content') || undefined,
    }
    const hasUTM = Object.values(utmParams).some(Boolean)

    return {
        utm_params: hasUTM ? utmParams : undefined,
        referrer_url: document.referrer || undefined,
    }
}

function formatPhoneNumber(value: string): string {
    const digits = value.replace(/\D/g, '').slice(0, 10)
    if (digits.length <= 3) return digits
    if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`
    return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6, 10)}`
}

function isValidEmail(email: string): boolean {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
}

function humanizeValidationError(field: string, message: string): string {
    const f = field.toLowerCase()
    const m = message.toLowerCase()

    if (f === 'phone' || m.includes('phone')) return 'Please enter a valid phone number.'
    if (f === 'email' || m.includes('email')) return 'Please enter a valid email address.'
    if (f === 'zip_code' || m.includes('zip')) return 'Please enter a valid 5-digit ZIP code.'
    if (f === 'insurance_provider' || m.includes('insurance')) return 'Please enter your insurance provider.'
    if (f === 'first_name' || f === 'last_name' || m.includes('name')) return 'Please enter your full name.'
    return message.replace(/^value error,\s*/i, '')
}

function extractErrorMessage(errorData: unknown, status: number): string {
    if (!errorData || typeof errorData !== 'object') {
        return `Server error (${status}). Please try again.`
    }

    const payload = errorData as Record<string, unknown>
    if (Array.isArray(payload.detail) && payload.detail.length > 0) {
        const first = payload.detail[0] as Record<string, unknown>
        const loc = Array.isArray(first.loc) ? first.loc : []
        const field = loc.length > 0 ? String(loc[loc.length - 1]) : 'field'
        const msg = typeof first.msg === 'string' ? first.msg : 'Please review your answers.'
        return humanizeValidationError(field, msg)
    }

    if (typeof payload.detail === 'string' && payload.detail.trim()) return payload.detail.trim()
    if (typeof payload.message === 'string' && payload.message.trim()) return payload.message.trim()

    return `Server error (${status}). Please try again.`
}

async function submitLeadToAPI(apiUrl: string, payload: Record<string, unknown>): Promise<LeadSubmitResponse> {
    const response = await fetch(`${apiUrl}/api/leads/submit`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
            'ngrok-skip-browser-warning': 'true',
        },
        body: JSON.stringify(payload),
    })

    if (!response.ok) {
        const errorData = await response.json().catch(() => null)
        throw new Error(extractErrorMessage(errorData, response.status))
    }

    return response.json()
}

function FieldLabel({
    htmlFor,
    children,
    required = false,
}: {
    htmlFor: string
    children: React.ReactNode
    required?: boolean
}) {
    return (
        <label htmlFor={htmlFor} className="assess-field-label">
            {children}
            {required ? <span className="assess-required">*</span> : null}
        </label>
    )
}

function SelectionCard({
    selected,
    onChange,
    label,
    description,
    type = 'radio',
    name,
}: {
    selected: boolean
    onChange: () => void
    label: string
    description?: string
    type?: 'checkbox' | 'radio'
    name?: string
}) {
    return (
        <label className={`assess-choice-card ${selected ? 'is-selected' : ''}`}>
            <input
                type={type}
                checked={selected}
                onChange={onChange}
                name={name}
                className={type === 'checkbox' ? 'nr-card-checkbox' : 'nr-card-radio'}
            />
            <div className="assess-choice-body">
                <div className="assess-choice-head">
                    <span className="assess-choice-label">{label}</span>
                </div>
                {description ? <span className="assess-choice-description">{description}</span> : null}
            </div>
        </label>
    )
}

function Logo({ logoUrl }: { logoUrl: string }) {
    return (
        <div className="assess-logo">
            <img
                src={logoUrl}
                alt="The Insomnia and Sleep Institute of Arizona"
                style={{ height: 48, width: 'auto', filter: 'brightness(0) invert(1)' }}
            />
            <div className="assess-logo-text">
                <span className="assess-logo-name">The Insomnia and Sleep Institute</span>
                <span className="assess-logo-sub">of Arizona</span>
            </div>
        </div>
    )
}

function ProgressBar({ current, total, stepName }: { current: number; total: number; stepName: string }) {
    const pct = Math.round((current / total) * 100)
    return (
        <div className="assess-progress">
            <div className="assess-progress-top">
                <span className="assess-progress-label">{stepName}</span>
                <span className="assess-progress-count">{current} of {total}</span>
            </div>
            <div className="assess-progress-bar">
                <div className="assess-progress-fill" style={{ width: `${pct}%` }} />
            </div>
        </div>
    )
}

function Footer() {
    return <footer className="assess-footer">Copyright {new Date().getFullYear()} The Insomnia and Sleep Institute of Arizona - All rights reserved</footer>
}

export const AssessmentPage: React.FC<AssessmentPageProps> = ({ apiUrl }) => {
    const [currentStep, setCurrentStep] = useState(1)
    const [formData, setFormData] = useState<AssessmentFormData>(INITIAL_FORM)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [submitError, setSubmitError] = useState<string | null>(null)
    const [submitResponse, setSubmitResponse] = useState<LeadSubmitResponse | null>(null)
    const [isCompleted, setIsCompleted] = useState(false)
    const [isAnimating, setIsAnimating] = useState(false)
    const submissionIdRef = useRef(generateSubmissionId())

    const logoUrl = `${apiUrl}/static/images/sleep-logo.png`

    useEffect(() => {
        setIsAnimating(true)
        const timer = window.setTimeout(() => setIsAnimating(false), 180)
        return () => window.clearTimeout(timer)
    }, [currentStep])

    const needsSmsConsent = formData.preferredContactMethod === 'text' || formData.preferredContactMethod === 'any'

    const canProceed = useMemo(() => {
        switch (currentStep) {
            case 1:
                return formData.hipaaConsent
            case 2:
                return formData.conditions.length > 0 && (!formData.conditions.includes('OTHER') || formData.conditionOther.trim().length > 1)
            case 3:
                return !!formData.sleepTreatmentInterest
            case 4:
                return !!formData.symptomDuration
            case 5:
                return formData.priorTreatments.length > 0
            case 6:
                return !!formData.urgency
            case 7:
                if (formData.isReferral === null) return false
                if (formData.isReferral && !formData.referringProviderName.trim()) return false
                if (formData.referringProviderEmail.trim() && !isValidEmail(formData.referringProviderEmail)) return false
                return true
            case 8:
                return (
                    formData.firstName.trim().length > 0 &&
                    formData.lastName.trim().length > 0 &&
                    isValidEmail(formData.email) &&
                    formData.phone.replace(/\D/g, '').length === 10
                )
            case 9:
                if (!formData.preferredContactMethod) return false
                return true
            case 10:
                if (formData.hasInsurance === null) return false
                if (formData.hasInsurance && !formData.insuranceProvider.trim()) return false
                return /^\d{5}$/.test(formData.zipCode.trim())
            default:
                return false
        }
    }, [currentStep, formData, needsSmsConsent])

    const updateField = <K extends keyof AssessmentFormData>(field: K, value: AssessmentFormData[K]) => {
        setFormData((prev) => ({ ...prev, [field]: value }))
    }

    const toggleCondition = (condition: ConditionType) => {
        setFormData((prev) => {
            const exists = prev.conditions.includes(condition)
            const nextConditions = exists ? prev.conditions.filter((item) => item !== condition) : [...prev.conditions, condition]
            return {
                ...prev,
                conditions: nextConditions,
                conditionOther: condition === 'OTHER' || nextConditions.includes('OTHER') ? prev.conditionOther : '',
            }
        })
    }

    const toggleTreatment = (treatment: TreatmentType) => {
        setFormData((prev) => {
            const currentlySelected = prev.priorTreatments.includes(treatment)
            if (treatment === 'NONE') {
                return { ...prev, priorTreatments: currentlySelected ? [] : ['NONE'] }
            }

            const withoutNone = prev.priorTreatments.filter((item) => item !== 'NONE')
            return {
                ...prev,
                priorTreatments: currentlySelected
                    ? withoutNone.filter((item) => item !== treatment)
                    : [...withoutNone, treatment],
            }
        })
    }

    const handleSubmit = async () => {
        if (!canProceed || isSubmitting) return

        setIsSubmitting(true)
        setSubmitError(null)

        try {
            const attribution = getMarketingAttribution()
            const primaryCondition = formData.conditions[0]

            const payload = {
                first_name: formData.firstName.trim(),
                last_name: formData.lastName.trim(),
                email: formData.email.trim(),
                phone: formData.phone.replace(/\D/g, ''),
                date_of_birth: formData.dateOfBirth || undefined,
                condition: primaryCondition,
                condition_other: formData.conditions.includes('OTHER') ? formData.conditionOther.trim() : undefined,
                conditions: formData.conditions,
                other_condition_text: formData.conditions.includes('OTHER') ? formData.conditionOther.trim() : undefined,
                sleep_treatment_interest: formData.sleepTreatmentInterest,
                preferred_contact_method: formData.preferredContactMethod || undefined,
                symptom_duration: formData.symptomDuration,
                prior_treatments: formData.priorTreatments,
                has_insurance: formData.hasInsurance,
                insurance_provider: formData.hasInsurance ? formData.insuranceProvider.trim() : undefined,
                zip_code: formData.zipCode.trim(),
                urgency: formData.urgency,
                hipaa_consent: formData.hipaaConsent,
                sms_consent: formData.smsConsent,
                is_referral: formData.isReferral === true,
                referring_provider_name: formData.isReferral ? formData.referringProviderName.trim() || undefined : undefined,
                referring_provider_specialty: formData.isReferral ? formData.referringProviderSpecialty.trim() || undefined : undefined,
                referring_clinic: formData.isReferral ? formData.referringClinic.trim() || undefined : undefined,
                referring_provider_email: formData.isReferral ? formData.referringProviderEmail.trim() || undefined : undefined,
                utm_params: attribution.utm_params,
                referrer_url: attribution.referrer_url,
                submission_id: submissionIdRef.current,
            }

            const response = await submitLeadToAPI(apiUrl, payload)
            setSubmitResponse(response)
            setIsCompleted(true)
        } catch (error) {
            if (error instanceof TypeError && error.message === 'Failed to fetch') {
                setSubmitError('Unable to connect to the server. Please try again.')
            } else if (error instanceof Error) {
                setSubmitError(error.message)
            } else {
                setSubmitError('An unexpected error occurred. Please try again.')
            }
        } finally {
            setIsSubmitting(false)
        }
    }

    const handleNext = () => {
        if (currentStep === TOTAL_INPUT_STEPS) {
            handleSubmit()
            return
        }
        setCurrentStep((prev) => Math.min(prev + 1, TOTAL_INPUT_STEPS))
    }

    const renderStep = () => {
        switch (currentStep) {
            case 1:
                return (
                    <div className="space-y-4">
                        <div className="space-y-2 assess-step-intro">
                            <h3>Welcome to Your Sleep Assessment</h3>
                            <p>Before we begin, please review our privacy practices and confirm that we may contact you about your sleep consultation.</p>
                        </div>

                        <div className="assess-privacy-card">
                            <h4>Privacy and HIPAA Notice</h4>
                            <p>
                                Your information is protected under HIPAA and will only be used to assess your sleep
                                needs and help our team contact you about care options.
                            </p>
                        </div>

                        <label className="assess-consent-card">
                            <input
                                type="checkbox"
                                checked={formData.hipaaConsent}
                                onChange={(event) => updateField('hipaaConsent', event.target.checked)}
                                className="nr-card-checkbox"
                            />
                            <span className="assess-consent-copy">
                                I acknowledge the privacy notice above and consent to the collection and use of my
                                health information.
                            </span>
                        </label>

                        <p className="assess-muted-note">
                            By continuing, you agree to our <a href="#" className="text-secondary-700 hover:underline">Terms</a> and <a href="#" className="text-secondary-700 hover:underline">Privacy Policy</a>.
                        </p>
                    </div>
                )
            case 2:
                return (
                    <div className="space-y-4">
                        <div className="space-y-2 assess-step-intro">
                            <h3>What sleep concerns would you like help with?</h3>
                            <p>Select all that apply. This helps us route you to the right specialist.</p>
                        </div>

                        <div className="space-y-2">
                            {CONDITION_OPTIONS.map((option) => (
                                <SelectionCard
                                    key={option.value}
                                    selected={formData.conditions.includes(option.value)}
                                    onChange={() => toggleCondition(option.value)}
                                    label={option.label}
                                    description={option.description}

                                    type="checkbox"
                                />
                            ))}
                        </div>

                        {formData.conditions.includes('OTHER') && (
                            <div className="space-y-2 animate-fade-in assess-field">
                                <FieldLabel htmlFor="condition-other" required>Tell us more about your sleep concern</FieldLabel>
                                <input
                                    id="condition-other"
                                    type="text"
                                    value={formData.conditionOther}
                                    onChange={(event) => updateField('conditionOther', event.target.value)}
                                    placeholder="Describe your sleep concern"
                                />
                            </div>
                        )}

                        {formData.conditions.length === 0 && (
                            <div className="assess-inline-hint">Please select at least one condition to continue.</div>
                        )}
                    </div>
                )
            case 3:
                return (
                    <div className="space-y-4">
                        <div className="space-y-2 assess-step-intro">
                            <h3>What are you most interested in exploring?</h3>
                            <p>Choose the option that best reflects why you are reaching out today.</p>
                        </div>

                        <div className="space-y-2">
                            {INTEREST_OPTIONS.map((option) => (
                                <SelectionCard
                                    key={option.value}
                                    selected={formData.sleepTreatmentInterest === option.value}
                                    onChange={() => updateField('sleepTreatmentInterest', option.value)}
                                    label={option.label}
                                    description={option.description}

                                    type="radio"
                                    name="sleep-interest"
                                />
                            ))}
                        </div>
                    </div>
                )
            case 4:
                return (
                    <div className="space-y-4">
                        <div className="space-y-2 assess-step-intro">
                            <h3>How long has this been affecting your sleep?</h3>
                            <p>This helps us understand how established the issue is before your consultation.</p>
                        </div>

                        <div className="space-y-2">
                            {DURATION_OPTIONS.map((option) => (
                                <SelectionCard
                                    key={option.value}
                                    selected={formData.symptomDuration === option.value}
                                    onChange={() => updateField('symptomDuration', option.value)}
                                    label={option.label}
                                    description={option.description}

                                    type="radio"
                                    name="duration"
                                />
                            ))}
                        </div>
                    </div>
                )
            case 5:
                return (
                    <div className="space-y-4">
                        <div className="space-y-2 assess-step-intro">
                            <h3>What have you already tried?</h3>
                            <p>Select every option that applies. We use this to understand your treatment history.</p>
                        </div>

                        <div className="space-y-2">
                            {TREATMENT_OPTIONS.map((option) => (
                                <SelectionCard
                                    key={option.value}
                                    selected={formData.priorTreatments.includes(option.value)}
                                    onChange={() => toggleTreatment(option.value)}
                                    label={option.label}
                                    description={option.description}

                                    type="checkbox"
                                />
                            ))}
                        </div>
                    </div>
                )
            case 6:
                return (
                    <div className="space-y-4">
                        <div className="space-y-2 assess-step-intro">
                            <h3>How soon would you like to speak with the clinic?</h3>
                            <p>Choose the timeline that best matches your current situation.</p>
                        </div>

                        <div className="space-y-2">
                            {URGENCY_OPTIONS.map((option) => (
                                <SelectionCard
                                    key={option.value}
                                    selected={formData.urgency === option.value}
                                    onChange={() => updateField('urgency', option.value)}
                                    label={option.label}
                                    description={option.description}

                                    type="radio"
                                    name="urgency"
                                />
                            ))}
                        </div>
                    </div>
                )
            case 7:
                return (
                    <div className="space-y-4">
                        <div className="space-y-2 assess-step-intro">
                            <h3>Were you referred by a provider?</h3>
                            <p>If yes, add the provider so we can tag the referral correctly and create the provider record.</p>
                        </div>

                        <div className="assess-choice-grid">
                            <SelectionCard
                                selected={formData.isReferral === true}
                                onChange={() => updateField('isReferral', true)}
                                label="Yes"
                                description="A provider referred me to the clinic."
                                type="radio"
                                name="referral"
                            />
                            <SelectionCard
                                selected={formData.isReferral === false}
                                onChange={() => updateField('isReferral', false)}
                                label="No"
                                description="I was not referred by a provider."
                                type="radio"
                                name="referral"
                            />
                        </div>

                        {formData.isReferral === true && (
                            <div className="space-y-3 animate-fade-in">
                                <div className="assess-field">
                                    <FieldLabel htmlFor="provider-name" required>Provider name</FieldLabel>
                                    <input
                                        id="provider-name"
                                        type="text"
                                        value={formData.referringProviderName}
                                        onChange={(event) => updateField('referringProviderName', event.target.value)}
                                        placeholder="Enter provider name"
                                    />
                                </div>

                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                    <div className="assess-field">
                                        <FieldLabel htmlFor="provider-specialty">Specialty</FieldLabel>
                                        <input
                                            id="provider-specialty"
                                            type="text"
                                            value={formData.referringProviderSpecialty}
                                            onChange={(event) => updateField('referringProviderSpecialty', event.target.value)}
                                            placeholder="Sleep medicine, pulmonology, neurology"
                                        />
                                    </div>
                                    <div className="assess-field">
                                        <FieldLabel htmlFor="provider-email">Provider email</FieldLabel>
                                        <input
                                            id="provider-email"
                                            type="email"
                                            value={formData.referringProviderEmail}
                                            onChange={(event) => updateField('referringProviderEmail', event.target.value)}
                                            placeholder="name@practice.com"
                                        />
                                    </div>
                                </div>

                                <div className="assess-field">
                                    <FieldLabel htmlFor="provider-clinic">Clinic or practice</FieldLabel>
                                    <input
                                        id="provider-clinic"
                                        type="text"
                                        value={formData.referringClinic}
                                        onChange={(event) => updateField('referringClinic', event.target.value)}
                                        placeholder="Practice name"
                                    />
                                </div>
                            </div>
                        )}
                    </div>
                )
            case 8:
                return (
                    <div className="space-y-4">
                        <div className="space-y-2 assess-step-intro">
                            <h3>How can we reach you?</h3>
                            <p>Your coordinator will use this information to follow up on your sleep assessment.</p>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div className="assess-field">
                                <FieldLabel htmlFor="first-name" required>First name</FieldLabel>
                                <input
                                    id="first-name"
                                    type="text"
                                    value={formData.firstName}
                                    onChange={(event) => updateField('firstName', event.target.value)}
                                    placeholder="First name"
                                />
                            </div>
                            <div className="assess-field">
                                <FieldLabel htmlFor="last-name" required>Last name</FieldLabel>
                                <input
                                    id="last-name"
                                    type="text"
                                    value={formData.lastName}
                                    onChange={(event) => updateField('lastName', event.target.value)}
                                    placeholder="Last name"
                                />
                            </div>
                        </div>

                        <div className="assess-field">
                            <FieldLabel htmlFor="email" required>Email address</FieldLabel>
                            <input
                                id="email"
                                type="email"
                                value={formData.email}
                                onChange={(event) => updateField('email', event.target.value)}
                                placeholder="you@example.com"
                            />
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div className="assess-field">
                                <FieldLabel htmlFor="phone" required>Phone number</FieldLabel>
                                <input
                                    id="phone"
                                    type="tel"
                                    value={formData.phone}
                                    onChange={(event) => updateField('phone', formatPhoneNumber(event.target.value))}
                                    placeholder="(480) 555-1234"
                                />
                            </div>
                            <div className="assess-field">
                                <FieldLabel htmlFor="dob">Date of birth</FieldLabel>
                                <input
                                    id="dob"
                                    type="date"
                                    value={formData.dateOfBirth}
                                    onChange={(event) => updateField('dateOfBirth', event.target.value)}
                                />
                            </div>
                        </div>
                    </div>
                )
            case 9:
                return (
                    <div className="space-y-4">
                        <div className="space-y-2 assess-step-intro">
                            <h3>How would you prefer us to follow up?</h3>
                            <p>Select your preferred contact method so we can reach you the way you prefer.</p>
                        </div>

                        <div className="assess-choice-grid">
                            {CONTACT_METHOD_OPTIONS.map((option) => {
                                return (
                                    <SelectionCard
                                        key={option.value}
                                        selected={formData.preferredContactMethod === option.value}
                                        onChange={() => {
                                            updateField('preferredContactMethod', option.value)
                                            if (option.value !== 'text' && option.value !== 'any') {
                                                updateField('smsConsent', false)
                                            }
                                        }}
                                        label={option.label}
                                        description={`Preferred ${option.label.toLowerCase()} follow-up`}
                                        type="radio"
                                        name="preferred-contact"
    
                                    />
                                )
                            })}
                        </div>
                    </div>
                )
            case 10:
                return (
                    <div className="space-y-4">
                        <div className="space-y-2 assess-step-intro">
                            <h3>Final details before you submit</h3>
                            <p>We use your insurance and ZIP code to verify coverage and service area.</p>
                        </div>

                        <div className="space-y-3">
                            <p className="assess-question-label">Do you have insurance?<span className="assess-required">*</span></p>
                            <div className="assess-choice-grid">
                                <SelectionCard
                                    selected={formData.hasInsurance === true}
                                    onChange={() => updateField('hasInsurance', true)}
                                    label="Yes, I have insurance"
                                    description="I want the clinic to review my coverage."
                                    type="radio"
                                    name="insurance"
                                />
                                <SelectionCard
                                    selected={formData.hasInsurance === false}
                                    onChange={() => updateField('hasInsurance', false)}
                                    label="No insurance"
                                    description="I do not have insurance for this evaluation."
                                    type="radio"
                                    name="insurance"
                                />
                            </div>
                        </div>

                        {formData.hasInsurance === true && (
                            <div className="space-y-2 animate-fade-in assess-field">
                                <FieldLabel htmlFor="insurance-provider" required>Insurance provider</FieldLabel>
                                <input
                                    id="insurance-provider"
                                    type="text"
                                    value={formData.insuranceProvider}
                                    onChange={(event) => updateField('insuranceProvider', event.target.value)}
                                    placeholder="Enter provider name"
                                />
                            </div>
                        )}

                        <div className="space-y-2 assess-field">
                            <FieldLabel htmlFor="zip-code" required>ZIP code</FieldLabel>
                            <input
                                id="zip-code"
                                type="text"
                                inputMode="numeric"
                                maxLength={5}
                                value={formData.zipCode}
                                onChange={(event) => updateField('zipCode', event.target.value.replace(/\D/g, '').slice(0, 5))}
                                placeholder="Enter ZIP"
                            />
                        </div>

                        {/* SMS Consent — last question before Submit */}
                        <div className="nr-sms-consent-card">
                            <label className="flex items-start gap-3 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={formData.smsConsent}
                                    onChange={(event) => updateField('smsConsent', event.target.checked)}
                                    className="nr-sms-checkbox mt-0.5"
                                />
                                <span className="text-sm text-gray-700">
                                    I consent to receive SMS messages about my assessment and scheduling. Message and
                                    data rates may apply. Reply STOP to opt out.
                                </span>
                            </label>
                        </div>
                    </div>
                )
            default:
                return null
        }
    }

    if (isCompleted) {
        return (
            <div className="nr-widget-root assess-page">
                <div className="assess-container">
                    <header className="assess-header">
                        <Logo logoUrl={logoUrl} />
                    </header>

                    <main className="assess-card" style={{ textAlign: 'center', padding: '40px 28px' }}>
                        <div
                            style={{
                                width: 56,
                                height: 56,
                                borderRadius: '50%',
                                background: '#C6F6D5',
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                marginBottom: 16,
                            }}
                        >
                            <Check color="#2F855A" size={28} />
                        </div>

                        <h2 style={{ fontSize: 24, fontWeight: 700, color: '#243448', marginBottom: 8 }}>Thank you</h2>
                        <p style={{ fontSize: 16, color: '#4A5568', maxWidth: 440, margin: '0 auto 20px', lineHeight: 1.6 }}>
                            {submitResponse?.message || 'Our care team will review your information and reach out soon.'}
                        </p>

                        {(submitResponse?.lead_number || submitResponse?.lead_id) && (
                            <div className="assess-success-reference">
                                <p style={{ fontSize: 11, color: '#2C5282', fontWeight: 600, marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                    Reference Number
                                </p>
                                <p style={{ fontSize: 18, fontWeight: 700, color: '#243448', fontFamily: 'monospace' }}>{submitResponse?.lead_number || submitResponse?.lead_id}</p>
                            </div>
                        )}

                        <div style={{ maxWidth: 340, margin: '0 auto', textAlign: 'left' }}>
                            <h4 style={{ fontSize: 14, fontWeight: 600, color: '#243448', marginBottom: 10 }}>What happens next?</h4>
                            {[
                                { n: '1', t: 'Review', d: 'A coordinator reviews your sleep assessment.' },
                                { n: '2', t: 'Contact', d: 'We reach out using your preferred contact method.' },
                                { n: '3', t: 'Consult', d: 'You discuss testing, treatment, or scheduling options.' },
                            ].map((item) => (
                                <div key={item.n} style={{ display: 'flex', gap: 10, marginBottom: 8 }}>
                                    <span
                                        style={{
                                            width: 22,
                                            height: 22,
                                            borderRadius: '50%',
                                            background: '#EBF4FF',
                                            color: '#243448',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            fontSize: 11,
                                            fontWeight: 700,
                                            flexShrink: 0,
                                        }}
                                    >
                                        {item.n}
                                    </span>
                                    <div>
                                        <p style={{ fontSize: 14, fontWeight: 600, color: '#243448', margin: 0 }}>{item.t}</p>
                                        <p style={{ fontSize: 12, color: '#718096', margin: 0 }}>{item.d}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </main>

                    <Footer />
                </div>
            </div>
        )
    }

    return (
        <div className="nr-widget-root assess-page">
            <div className="assess-container">
                <header className="assess-header">
                    <Logo logoUrl={logoUrl} />
                    <div className="assess-header-right">
                        <span className="assess-header-title">Free Assessment</span>
                        <span className="assess-header-sub">~2 min - Confidential</span>
                    </div>
                </header>

                <main className="assess-card">
                    <ProgressBar current={currentStep} total={TOTAL_INPUT_STEPS} stepName={STEP_NAMES[currentStep - 1]} />

                    <div
                        className="assess-step-content"
                        style={{
                            opacity: isAnimating ? 0 : 1,
                            transform: isAnimating ? 'translateX(8px)' : 'translateX(0)',
                            transition: 'opacity 0.18s ease, transform 0.18s ease',
                        }}
                    >
                        {renderStep()}
                    </div>

                    {submitError && (
                        <div className="assess-error">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#C53030" strokeWidth="2">
                                <circle cx="12" cy="12" r="10" />
                                <line x1="15" y1="9" x2="9" y2="15" />
                                <line x1="9" y1="9" x2="15" y2="15" />
                            </svg>
                            <span>{submitError}</span>
                        </div>
                    )}

                    <div className="assess-nav">
                        {currentStep > 1 ? (
                            <button className="assess-btn-back" onClick={() => setCurrentStep((prev) => Math.max(prev - 1, 1))} disabled={isSubmitting}>
                                <ChevronLeft size={16} />
                                Back
                            </button>
                        ) : (
                            <div />
                        )}

                        <button className="assess-btn-next" onClick={handleNext} disabled={!canProceed || isSubmitting}>
                            {isSubmitting ? (
                                <>
                                    <span className="assess-spinner" />
                                    Submitting...
                                </>
                            ) : currentStep === TOTAL_INPUT_STEPS ? (
                                <>Submit Assessment</>
                            ) : (
                                <>
                                    Continue
                                    <ChevronRight size={16} />
                                </>
                            )}
                        </button>
                    </div>
                </main>

                {currentStep === 1 ? (
                    <div className="assess-hipaa-notice">
                        <Shield size={16} />
                        <div>
                            <strong>Privacy and HIPAA Notice</strong>
                            <p>Your information is protected under HIPAA and will only be used to assess your sleep needs and contact you about care.</p>
                        </div>
                    </div>
                ) : (
                    <div className="assess-trust-footer">
                        <span className="flex items-center gap-1"><Lock size={13} /> Confidential</span>
                        <span className="flex items-center gap-1"><Shield size={13} /> HIPAA</span>
                        <span className="flex items-center gap-1"><Lock size={13} /> 256-bit</span>
                    </div>
                )}

                <Footer />
            </div>
        </div>
    )
}

export default AssessmentPage
