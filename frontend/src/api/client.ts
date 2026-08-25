import { message } from 'antd'
import { client } from '@/client/client.gen'
import { getAuthToken, useAuthStore } from '@/stores/authStore'
import { formatApiError } from '@/utils/errors'

client.setConfig({
    baseUrl: '',
    throwOnError: true,
})

client.interceptors.request.use((request) => {
// 登录 / 健康检查这类公共接口不应该带 token；如果没有就跳过
    const token = getAuthToken()
    if (token && !request.headers.has('Authorization')) {
        request.headers.set('Authorization', `Bearer ${token}`)
    }
    return request
})


// 让 /login 跳转只发生一次，避免拦截到多个并发 401 后疯狂 replace
let redirectingToLogin = false


client.interceptors.response.use(async (response) => {
    if (response.status === 401) {
        useAuthStore.getState().logout()
        if (!redirectingToLogin && window.location.pathname !== '/login') {
            redirectingToLogin = true
            const back = window.location.pathname + window.location.search
            window.location.replace(`/login?back=${encodeURIComponent(back)}`)
        }
// 在登录页时展示后端返回的错误（如"用户名或密码错误"）
        if (window.location.pathname === '/login') {
            message.error(await formatApiError(response))
        }
        return response
    }
    if (!response.ok) {
        message.error(await formatApiError(response))
    }
    return response
})