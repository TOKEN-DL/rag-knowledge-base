import { fetchEventSource } from '@microsoft/fetch-event-source'
import type { AgentStep, CitationRead, QueryRouteRead } from '@/client/types.gen'


export interface ChatStartEvent {
    type: 'start'
    /** LangSmith trace_id；未启用观测时为 null */
    traceId: string | null
    /** LangSmith UI 跳转 URL；后端按 LANGSMITH_RUN_URL_PREFIX 拼好下发，未配置为 null */
    traceUrl: string | null
}

export interface ChatAgentStepsEvent {
    type: 'agent_steps'
    steps: AgentStep[]
}

export interface ChatCitationsEvent {
    type: 'citations'
    citations: CitationRead[]
}

export interface ChatQueryRouteEvent {
    type: 'query_route'
    queryRoute: QueryRouteRead
}

export interface ChatTokenEvent {
    type: 'token'
    delta: string
}
export interface ChatEndEvent {
    type: 'end'
    message_id: string
    refused: boolean
}
export interface ChatErrorEvent {
    type: 'error'
    code: string
    message: string
}


export interface ChatVerifyResultEvent {
    type: 'verify_result'
    verified: boolean
    reason: string | null
    replacementAnswer: string | null
}

export type ChatStreamEvent =
    | ChatStartEvent
    | ChatQueryRouteEvent
    | ChatAgentStepsEvent
    | ChatCitationsEvent
    | ChatTokenEvent
    | ChatVerifyResultEvent
    | ChatEndEvent
    | ChatErrorEvent



interface StreamChatParams {
    conversationId: string
    question: string
    signal?: AbortSignal
    onEvent: (event: ChatStreamEvent) => void
}

class FatalSseError extends Error {}


import {getAuthToken, useAuthStore } from "@/stores/authStore.ts";
export async function streamChat({
    conversationId,
    question,
    signal,
    onEvent,
}: StreamChatParams): Promise<void> {
    const token = getAuthToken()
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) {
        headers.Authorization = `Bearer ${token}`
    }
    await fetchEventSource(
        `/api/conversations/${conversationId}/chat`,
        {
            method: 'POST',
            headers,
            body: JSON.stringify({ question }),
            signal,
// 默认会在 tab 切换到后台时关闭连接，问答场景不希望中断
            openWhenHidden: true,
            async onopen(response) {
                if (response.status === 401) {
                    useAuthStore.getStatus().logout()
                    if (window.location.pathname !== '/login') {
                        const back = window.location.pathname + window.location.search
                        window.location.replace(`/login?back=${encodeURIComponent(back)}`)
                    }
                    throw new FatalSseError("请先登录")
                }
                if (response.ok && response.headers.get('content-type')?.includes('text/event-stream')) {
                    return
                }
                const text = await response.text().catch(() => '')
                throw new FatalSseError(text || `HTTP ${response.status}`)
            },
            onmessage(msg) {
                if (!msg.event) return
                const data = msg.data ? JSON.parse(msg.data) : {}
                switch (msg.event) {
                    case 'message_start':
                        onEvent({
                            type: 'start',
                            traceId: data.trace_id ?? null,
                            traceUrl: data.trace_url ?? null,
                        })
                        break
                    case 'query_route':
                        onEvent({type: 'query_route', queryRoute: data as QueryRouteRead})
                        break
                    case 'agent_steps':
                        onEvent({ type: 'agent_steps', steps: (data.steps ?? []) as AgentStep[] })
                        break
                    case 'citations':
                        onEvent({ type: 'citations', citations: data.citations ?? [] })
                        break
                    case 'token':
                        onEvent({ type: 'token', delta: data.delta ?? '' })
                        break
                    case 'verify_result':
                        onEvent({
                            type: 'verify_result',
                            verified: Boolean(data.verified),
                            reason: data.reason ?? null,
                            replacementAnswer: data.replacementAnswer ?? null,

                        })
                        break
                    case 'message_end':
                        onEvent({
                            type: 'end',
                            message_id: data.message_id,
                            refused: Boolean(data.refused),
                        })
                        break
                    case 'error':
                        onEvent({ type: 'error', code: data.code ?? 'error', message: data.message ?? '请求失败' })
                        break
                }
            },
            onclose() {
// 服务端正常关闭流；不抛错让上层走 finally 收尾
            },
            onerror(err) {
                throw err
            },
        },
    )
}


