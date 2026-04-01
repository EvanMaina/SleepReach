import api from '../lib/api'

export interface Attachment {
    id: string
    lead_id: string
    filename: string
    stored_filename: string
    file_type: string
    file_size: number
    uploaded_by: string | null
    uploaded_by_id: string | null
    created_at: string
}

export type AttachmentCountMap = Record<string, number>

export const ATTACHMENTS_CHANGED_EVENT = 'sleepreach:attachments-changed'

export function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function notifyAttachmentsChanged(leadId: string): void {
    window.dispatchEvent(new CustomEvent(ATTACHMENTS_CHANGED_EVENT, { detail: { leadId } }))
}

export async function uploadAttachment(leadId: string, file: File): Promise<Attachment> {
    const formData = new FormData()
    formData.append('file', file)

    const response = await api.post(`/leads/${leadId}/attachments`, formData, {
        headers: { 'Content-Type': undefined as unknown as string },
        timeout: 60000,
    })
    return response.data
}

export async function listAttachments(leadId: string): Promise<Attachment[]> {
    const response = await api.get(`/leads/${leadId}/attachments`)
    return response.data || []
}

export async function deleteAttachment(leadId: string, attachmentId: string): Promise<{ success: boolean; message: string }> {
    const response = await api.delete(`/leads/${leadId}/attachments/${attachmentId}`)
    return response.data
}

export async function downloadAttachment(leadId: string, attachmentId: string, filename: string): Promise<void> {
    const response = await api.get(`/leads/${leadId}/attachments/${attachmentId}/download`, {
        responseType: 'blob',
    })

    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', filename)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
}

export async function getAttachmentCounts(): Promise<AttachmentCountMap> {
    const response = await api.get('/leads/attachment-counts')
    return response.data || {}
}
