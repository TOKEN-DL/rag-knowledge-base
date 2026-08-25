import { Result } from 'antd'
import { Outlet } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
export function RequireAdmin() {
    const user = useAuthStore((s) => s.user)
    if (!user?.isAdmin) {
        return (
            <Result
                status="403"
                title="403"
                subTitle="此页面仅管理员可访问"
            />
        )
    }
    return <Outlet />
}