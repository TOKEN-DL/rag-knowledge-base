import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
    createRole as sdkCreateRole,
    deleteRole as sdkDeleteRole,
    listRoles as sdkListRoles,
    updateRole as sdkUpdateRole,
} from '@/client/sdk.gen'
import type { RoleCreate, RoleUpdate } from '@/client/types.gen'
import { rolesListKey } from '@/api/queryKeys'


export function useRoles() {
    return useQuery({
        queryKey: rolesListKey,
        queryFn: async () => (await sdkListRoles()).data,
    })
}


export function useCreateRoleMutation() {
    const client = useQueryClient()
    return useMutation({
        mutationFn: async (payload: RoleCreate) =>
            (await sdkCreateRole({ body: payload })).data,
        onSuccess: () => {
            void client.invalidateQueries({ queryKey: rolesListKey })
        },
    })
}

export function useUpdateRoleMutation() {
    const client = useQueryClient()
    return useMutation({
        mutationFn: async (params: { roleId: string; body: RoleUpdate }) =>
            (
                await sdkUpdateRole({
                    path: { role_id: params.roleId },
                    body: params.body,
                })
            ).data,
        onSuccess: () => {
            void client.invalidateQueries({ queryKey: rolesListKey })
        },
    })
}

export function useDeleteRoleMutation() {
    const client = useQueryClient()
    return useMutation({
        mutationFn: async (roleId: string) =>
            sdkDeleteRole({ path: { role_id: roleId } }),
        onSuccess: () => {
            void client.invalidateQueries({ queryKey: rolesListKey })
        },
    })
}