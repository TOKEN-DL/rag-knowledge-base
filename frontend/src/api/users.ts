import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
    createUser as sdkCreateUser,
    deleteUser as sdkDeleteUser,
    listUsers as sdkListUsers,
    updateUser as sdkUpdateUser,
} from '@/client/sdk.gen'
import type {
    UserCreate,
    UserUpdate,
} from '@/client/types.gen'


export function useUsers(page = 1, pageSize = 20) {
    return useQuery({
        queryKey: ['users', { page, pageSize }],
        queryFn: async () =>
            (await sdkListUsers({ query: { page, page_size: pageSize } })).data,
    })
}


export function useCreateUserMutation() {
    const client = useQueryClient()
    return useMutation({
        mutationFn: async (payload: UserCreate) =>
            (await sdkCreateUser({ body: payload })).data,
        onSuccess: () => {
            void client.invalidateQueries({ queryKey: ['users'] })
        },
    })

}

export function useUpdateUserMutation() {
    const client = useQueryClient()
    return useMutation({
        mutationFn: async (params: { userId: string; body: UserUpdate }) =>
            (
                await sdkUpdateUser({
                    path: { user_id: params.userId },
                    body: params.body,
                })
            ).data,
        onSuccess: () => {
            void client.invalidateQueries({ queryKey: ['users'] })
        },
    })
}

export function useDeleteUserMutation() {
    const client = useQueryClient()
    return useMutation({
        mutationFn: async (userId: string) =>
            sdkDeleteUser({ path: { user_id: userId } }),
        onSuccess: () => {
            void client.invalidateQueries({ queryKey: ['users'] })
        },
    })
}