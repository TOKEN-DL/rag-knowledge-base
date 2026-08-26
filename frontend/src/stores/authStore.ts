import { create } from 'zustand'

const TOKEN_KEY = 'rag-kb.auth.token'
const USER_KEY = 'rag-kb.auth.user'


export interface AuthUser {
    id: string
    username: string
    displayName: string
    permissionTags: string[]
    isAdmin: boolean
    roleNames: string[]
}


interface AuthState {
    token: string | null
    user: AuthUser | null
    ready: boolean
    setAuth: (token: string, user: AuthUser) => void
    setUser: (user: AuthUser) => void
    logout: () => void
    hasToken: () => boolean
    hydrate: () => void
}


function loadUser(): AuthUser | null {
    const raw = localStorage.getItem(USER_KEY)
    if (!raw) return null
    try {
        return JSON.parse(raw) as AuthUser
    } catch {
        return null
    }
}




export const useAuthStore = create<AuthState>((set, get) => ({
    token: null,
    user: null,
    ready: false,

    setAuth: (token, user) => {
        localStorage.setItem(TOKEN_KEY, token)
        localStorage.setItem(USER_KEY, JSON.stringify(user))
        set({ token, user })
    },

    setUser: (user) => {
        localStorage.setItem(USER_KEY, JSON.stringify(user))
        set({ user })
    },

    logout: () => {
        localStorage.removeItem(TOKEN_KEY)
        localStorage.removeItem(USER_KEY)
        set({ token: null, user: null })
    },

    hasToken: () => Boolean(get().token),

    hydrate: () => {
        const token = localStorage.getItem(TOKEN_KEY)
        const user = loadUser()
        set({ token, user, ready: true })
    },
}))


/** 给 SSE / 拦截器用：直接读最新 token，不订阅 store。 */
export function getAuthToken(): string | null {
    return useAuthStore.getState().token
}