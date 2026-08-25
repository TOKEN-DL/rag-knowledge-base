import {
    getCurrentUser as sdkGetCurrentUser,
    login as sdkLogin,
} from '@/client/sdk.gen'
import type { LoginResponse, MeResponse, UserRead } from '@/client/types.gen'
import type { AuthUser } from '@/stores/authStore'
function toAuthUser(payload: LoginResponse | MeResponse): AuthUser {
// openapi-ts 会把有 default 的字段标成 optional；这里统一兜空数组，避免下游每处 ?? []
    const user = payload.user as UserRead
    return {
        id: user.id,
        username: user.username,
        displayName: user.display_name,
        permissionTags: payload.permission_tags ?? [],
        isAdmin: payload.is_admin,
        roleNames: user.roles?.map((r) => r.name) ?? [],
    }
}

export interface LoginResult {
    token: string
    user: AuthUser
}

export async function login(username: string, password: string): Promise<LoginResult> {
    const { data } = await sdkLogin({ body: { username, password } })
    if (!data) {
        throw new Error('登录失败')
    }
    return { token: data.access_token, user: toAuthUser(data) }
}

export async function fetchCurrentUser(): Promise<AuthUser> {
    const { data } = await sdkGetCurrentUser()
    if (!data) throw new Error('获取用户信息失败')
    return toAuthUser(data)
}