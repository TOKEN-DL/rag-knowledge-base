import { useState } from 'react'
import {
    App,
    Button,
    Form,
    Input,
    Modal,
    Popconfirm,
    Select,
    Space,
    Table,
    Tag,
    Typography,
} from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
    useCreateUserMutation,
    useDeleteUserMutation,
    useUpdateUserMutation,
    useUsers,
} from '@/api/users'
import { useRoles } from '@/api/roles'
import { useAuthStore } from '@/stores/authStore'
import type { RoleRead, UserRead } from '@/client/types.gen'

const { Title, Paragraph } = Typography

const STATUS_OPTIONS = [
    { value: 'active', label: '启用' },
    { value: 'disabled', label: '禁用' },
] as const

const STATUS_TAG: Record<UserRead['status'], { color: string; label: string }> = {
    active: { color: 'success', label: '启用' },
    disabled: { color: 'default', label: '禁用' },
}

export function UsersPage() {
    const [page, setPage] = useState(1)
    const [pageSize, setPageSize] = useState(20)
    const listQuery = useUsers(page, pageSize)
    const rolesQuery = useRoles()
    const [createOpen, setCreateOpen] = useState(false)
    const [editing, setEditing] = useState<UserRead | null>(null)

    const columns: ColumnsType<UserRead> = [
        {
            title: '用户名',
            dataIndex: 'username',
            width: 140,
        },
        {
            title: '显示名',
            dataIndex: 'display_name',
            width: 160,
        },
        {
            title: '状态',
            dataIndex: 'status',
            width: 100,
            render: (status: UserRead['status']) => {
                const tag = STATUS_TAG[status]
                return <Tag color={tag.color}>{tag.label}</Tag>
            },
        },
        {
            title: '角色',
            key: 'roles',
            render: (_, record) => {
                const roles = record.roles ?? []
                if (roles.length === 0) return <Tag>无</Tag>
                return (
                    <Space size={4} wrap>
                        {roles.map((r) => (
                            <Tag color="blue" key={r.id}>{r.name}</Tag>
                        ))}
                    </Space>
                )
            },
        },
        {
            title: '创建时间',
            dataIndex: 'created_at',
            width: 200,
            render: (value: string) => new Date(value).toLocaleString('zh-CN'),
        },
        {
            title: '操作',
            key: 'actions',
            width: 160,
            render: (_, record) => (
                <UserRowActions
                    record={record}
                    onEdit={() => setEditing(record)}
                />
            ),
        },
    ]

    return (
        <div>
            <Title level={3}>用户管理</Title>
            <Paragraph type="secondary">
                创建、禁用用户，并分配角色。同一用户的“基础字段”和“角色”通过两次请求提交，避免 password 校验与角色变更相互干扰。
            </Paragraph>
            <Space style={{ marginBottom: 16 }} wrap>
                <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    onClick={() => setCreateOpen(true)}
                >
                    新建用户
                </Button>
                <Button
                    icon={<ReloadOutlined />}
                    onClick={() => listQuery.refetch()}
                    loading={listQuery.isFetching}
                >
                    刷新
                </Button>
            </Space>
            <Table<UserRead>
                rowKey="id"
                loading={listQuery.isLoading}
                columns={columns}
                dataSource={listQuery.data?.items ?? []}
                pagination={{
                    current: page,
                    pageSize,
                    total: listQuery.data?.total ?? 0,
                    showSizeChanger: true,
                    onChange: (nextPage, nextSize) => {
                        setPage(nextPage)
                        setPageSize(nextSize)
                    },
                }}
            />
            <CreateUserModal
                open={createOpen}
                roleOptions={rolesQuery.data ?? []}
                onClose={() => setCreateOpen(false)}
            />
            <EditUserModal
                target={editing}
                roleOptions={rolesQuery.data ?? []}
                onClose={() => setEditing(null)}
            />
        </div>
    )
}

function UserRowActions({
    record,
    onEdit,
}: {
    record: UserRead
    onEdit: () => void
}) {
    const { message } = App.useApp()
    const currentUserId = useAuthStore((s) => s.user?.id)
    const deleteMutation = useDeleteUserMutation()
    const isSelf = record.id === currentUserId

    return (
        <Space>
            <Button
                type="link"
                size="small"
                icon={<EditOutlined />}
                onClick={onEdit}
            >
                编辑
            </Button>
            <Popconfirm
                title="删除该用户？"
                okType="danger"
                disabled={isSelf}
                onConfirm={async () => {
                    try {
                        await deleteMutation.mutateAsync(record.id)
                        message.success('已删除')
                    } catch {
                        // 拦截器已弹过 message.error
                    }
                }}
            >
                <Button
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    disabled={isSelf}
                    title={isSelf ? '不能删除自己' : ''}
                >
                    删除
                </Button>
            </Popconfirm>
        </Space>
    )
}

interface CreateFormValues {
    username: string
    password: string
    display_name: string
    role_ids?: string[]
}

function CreateUserModal({
    open,
    roleOptions,
    onClose,
}: {
    open: boolean
    roleOptions: RoleRead[]
    onClose: () => void
}) {
    const { message } = App.useApp()
    const [form] = Form.useForm<CreateFormValues>()
    const createMutation = useCreateUserMutation()

    const handleClose = () => {
        form.resetFields()
        onClose()
    }

    return (
        <Modal
            title="新建用户"
            open={open}
            onCancel={handleClose}
            destroyOnClose
            confirmLoading={createMutation.isPending}
            okText="创建"
            cancelText="取消"
            onOk={async () => {
                try {
                    const values = await form.validateFields()
                    await createMutation.mutateAsync({
                        username: values.username,
                        password: values.password,
                        display_name: values.display_name,
                        role_ids: values.role_ids ?? [],
                    })
                    message.success('已创建')
                    form.resetFields()
                    onClose()
                } catch {
                    // validateFields 失败时 antd 已经展示行内错误
                    // mutation 失败时拦截器已展示
                    // 这里只兜住异常，避免抛到 UI
                    form.resetFields()
                    onClose()
                }
            }}
        >
            <Form<CreateFormValues>
                form={form}
                layout="vertical"
                initialValues={{ username: '', password: '', display_name: '' }}
            >
                <Form.Item
                    name="username"
                    label="用户名"
                    rules={[{ required: true, message: '请输入用户名' }]}
                >
                    <Input autoFocus placeholder="登录用户名" />
                </Form.Item>
                <Form.Item
                    name="password"
                    label="密码"
                    rules={[{ required: true, message: '请输入密码' }, { min: 6, message: '至少 6 位' }]}
                >
                    <Input.Password placeholder="至少 6 位" />
                </Form.Item>
                <Form.Item
                    name="display_name"
                    label="显示名"
                    rules={[{ required: true, message: '请输入显示名' }]}
                >
                    <Input placeholder="界面展示的姓名/昵称" />
                </Form.Item>
                <Form.Item name="role_ids" label="角色">
                    <Select
                        mode="multiple"
                        allowClear
                        placeholder="可选：分配角色"
                        options={roleOptions.map((r) => ({ value: r.id, label: r.name }))}
                    />
                </Form.Item>
            </Form>
        </Modal>
    )
}

interface EditFormValues {
    display_name: string
    status: UserRead['status']
    password?: string
    role_ids: string[]
}

function EditUserModal({
    target,
    roleOptions,
    onClose,
}: {
    target: UserRead | null
    roleOptions: RoleRead[]
    onClose: () => void
}) {
    const { message } = App.useApp()
    const [form] = Form.useForm<EditFormValues>()
    const updateMutation = useUpdateUserMutation()

    const handleClose = () => {
        form.resetFields()
        onClose()
    }

    async function onFinish(values: EditFormValues) {
        if (!target) return
        try {
            // TODO: 后端 UserUpdate 当前不支持 role_ids，编辑角色需要后端先加 PUT /api/users/{id}/roles
            await updateMutation.mutateAsync({
                userId: target.id,
                body: {
                    display_name: values.display_name,
                    status: values.status,
                    password: values.password ? values.password : null,
                },
            })
            message.success('已保存基础字段（角色变更暂未接入，需后端先实现）')
            form.resetFields()
            onClose()
        } catch {
            // 拦截器已展示 error，避免抛到 UI
        }
    }

    return (
        <Modal
            title={target ? `编辑用户：${target.username}` : '编辑用户'}
            open={Boolean(target)}
            onCancel={handleClose}
            destroyOnClose
            okText="保存"
            cancelText="取消"
            confirmLoading={updateMutation.isPending}
            onOk={async () => {
                try {
                    const values = await form.validateFields()
                    await onFinish(values)
                } catch {
                    // validateFields 失败时 antd 已经展示行内错误
                }
            }}
        >
            <Form<EditFormValues>
                form={form}
                layout="vertical"
                preserve={false}
                initialValues={
                    target
                        ? {
                            display_name: target.display_name,
                            status: target.status,
                            password: '',
                            role_ids: (target.roles ?? []).map((r) => r.id),
                        }
                        : undefined
                }
                // 每次 target 变化重置表单
                key={target?.id ?? 'empty'}
            >
                <Form.Item
                    name="display_name"
                    label="显示名"
                    rules={[{ required: true, message: '请输入显示名' }]}
                >
                    <Input />
                </Form.Item>
                <Form.Item
                    name="status"
                    label="状态"
                    rules={[{ required: true, message: '请选择状态' }]}
                >
                    <Select options={[...STATUS_OPTIONS]} />
                </Form.Item>
                <Form.Item
                    name="password"
                    label="重置密码"
                    tooltip="留空表示不修改密码"
                    rules={[
                        {
                            validator: (_, value: string | undefined) =>
                                !value || value.length >= 6
                                    ? Promise.resolve()
                                    : Promise.reject(new Error('至少 6 位')),
                        },
                    ]}
                >
                    <Input.Password placeholder="留空则不修改" />
                </Form.Item>
                <Form.Item name="role_ids" label="角色">
                    <Select
                        mode="multiple"
                        allowClear
                        placeholder="分配角色"
                        options={roleOptions.map((r) => ({ value: r.id, label: r.name }))}
                    />
                </Form.Item>
            </Form>
        </Modal>
    )
}