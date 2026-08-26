import { useState } from 'react'
import {
    App,
    Button,
    Form,
    Input,
    Modal,
    Popconfirm,
    Space,
    Table,
    Tag,
    Tooltip,
    Typography,
} from 'antd'
import {
    DeleteOutlined,
    EditOutlined,
    PlusOutlined,
    ReloadOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
    useCreateRoleMutation,
    useDeleteRoleMutation,
    useRoles,
    useUpdateRoleMutation,
} from '@/api/roles'
import { PermissionTagsField } from '@/components/PermissionTagsField'
import type { RoleRead } from '@/client/types.gen'

const { Title, Paragraph } = Typography

// 'admin' 是策略代码锚点（见 types.gen.ts 中 RoleUpdate 的注释），不允许改名/删除
const PROTECTED_ROLE_NAMES: ReadonlySet<string> = new Set(['admin'])

export function RolesPage() {
    const listQuery = useRoles()
    const [createOpen, setCreateOpen] = useState(false)
    const [editing, setEditing] = useState<RoleRead | null>(null)

    const columns: ColumnsType<RoleRead> = [
        {
            title: '角色名',
            dataIndex: 'name',
            width: 160,
            render: (name: string) =>
                PROTECTED_ROLE_NAMES.has(name) ? (
                    <Tag color="gold">{name}</Tag>
                ) : (
                    <Tag color="blue">{name}</Tag>
                ),
        },
        {
            title: '说明',
            dataIndex: 'description',
            ellipsis: true,
        },
        {
            title: '权限标签',
            key: 'permission_tags',
            width: 260,
            render: (_, record) => {
                const tags = record.permission_tags ?? []
                if (tags.length === 0) return <Tag>无</Tag>
                return (
                    <Space size={4} wrap>
                        {tags.map((t) => (
                            <Tag color={t === '*' ? 'gold' : 'blue'} key={t}>
                                {t}
                            </Tag>
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
                <RoleRowActions
                    record={record}
                    onEdit={() => setEditing(record)}
                />
            ),
        },
    ]

    return (
        <div>
            <Title level={3}>角色管理</Title>
            <Paragraph type="secondary">
                角色是权限标签的集合。用户被授予角色后，将自动获得该角色下所有标签对应的文档访问权限。
                系统内置 <Tag color="gold">admin</Tag> 角色不允许改名或删除。
            </Paragraph>
            <Space style={{ marginBottom: 16 }} wrap>
                <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    onClick={() => setCreateOpen(true)}
                >
                    新建角色
                </Button>
                <Button
                    icon={<ReloadOutlined />}
                    onClick={() => listQuery.refetch()}
                    loading={listQuery.isFetching}
                >
                    刷新
                </Button>
            </Space>
            <Table<RoleRead>
                rowKey="id"
                loading={listQuery.isLoading}
                columns={columns}
                dataSource={listQuery.data ?? []}
                pagination={false}
            />
            <CreateRoleModal
                open={createOpen}
                onClose={() => setCreateOpen(false)}
            />
            <EditRoleModal
                target={editing}
                onClose={() => setEditing(null)}
            />
        </div>
    )
}

function RoleRowActions({
    record,
    onEdit,
}: {
    record: RoleRead
    onEdit: () => void
}) {
    const { message } = App.useApp()
    const deleteMutation = useDeleteRoleMutation()
    const isProtected = PROTECTED_ROLE_NAMES.has(record.name)

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
            <Tooltip title={isProtected ? '内置角色，不能删除' : ''}>
                <Popconfirm
                    title={`删除角色 “${record.name}”？`}
                    description="已被分配该角色的用户将自动失去这些权限标签。"
                    okType="danger"
                    disabled={isProtected}
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
                        disabled={isProtected}
                    >
                        删除
                    </Button>
                </Popconfirm>
            </Tooltip>
        </Space>
    )
}

interface CreateFormValues {
    name: string
    description?: string
    permission_tags?: string[]
}

function CreateRoleModal({ open, onClose }: { open: boolean; onClose: () => void }) {
    const { message } = App.useApp()
    const [form] = Form.useForm<CreateFormValues>()
    const createMutation = useCreateRoleMutation()

    const handleClose = () => {
        form.resetFields()
        onClose()
    }

    return (
        <Modal
            title="新建角色"
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
                        name: values.name.trim(),
                        description: values.description?.trim() || undefined,
                        permission_tags: values.permission_tags ?? [],
                    })
                    message.success('已创建')
                    form.resetFields()
                    onClose()
                } catch {
                    // validateFields / mutation 失败时 antd/拦截器已展示
                }
            }}
        >
            <Form<CreateFormValues>
                form={form}
                layout="vertical"
                preserve={false}
                initialValues={{ name: '', description: '', permission_tags: [] }}
            >
                <Form.Item
                    name="name"
                    label="角色名"
                    rules={[
                        { required: true, message: '请输入角色名' },
                        { max: 64 },
                        {
                            validator: (_, value: string) =>
                                PROTECTED_ROLE_NAMES.has(value?.trim())
                                    ? Promise.reject(new Error('该角色名被系统保留'))
                                    : Promise.resolve(),
                        },
                    ]}
                >
                    <Input autoFocus placeholder="例如：finance、hr" />
                </Form.Item>
                <Form.Item name="description" label="说明">
                    <Input.TextArea
                        autoSize={{ minRows: 2, maxRows: 4 }}
                        placeholder="可选：描述该角色的用途"
                    />
                </Form.Item>
                <Form.Item
                    name="permission_tags"
                    label="权限标签"
                    tooltip="持有任一相同标签的用户即可访问该标签下的文档"
                >
                    <PermissionTagsField placeholder="输入标签后回车，例如 finance、hr" />
                </Form.Item>
            </Form>
        </Modal>
    )
}

interface EditFormValues {
    description?: string
    permission_tags?: string[]
}

function EditRoleModal({
    target,
    onClose,
}: {
    target: RoleRead | null
    onClose: () => void
}) {
    const { message } = App.useApp()
    const [form] = Form.useForm<EditFormValues>()
    const updateMutation = useUpdateRoleMutation()
    const isProtected = target ? PROTECTED_ROLE_NAMES.has(target.name) : false

    const handleClose = () => {
        form.resetFields()
        onClose()
    }

    async function onFinish(values: EditFormValues) {
        if (!target) return
        try {
            // 名称不允许改动（策略代码以角色名为锚）
            await updateMutation.mutateAsync({
                roleId: target.id,
                body: {
                    description: values.description ?? null,
                    permission_tags: values.permission_tags ?? null,
                },
            })
            message.success('已保存')
            form.resetFields()
            onClose()
        } catch {
            // 拦截器已展示 error
        }
    }

    return (
        <Modal
            title={target ? `编辑角色：${target.name}` : '编辑角色'}
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
                            description: target.description,
                            permission_tags: target.permission_tags ?? [],
                        }
                        : undefined
                }
                // 切换 target 时重置整个表单
                key={target?.id ?? 'empty'}
            >
                <Form.Item label="角色名">
                    <Input value={target?.name} disabled />
                </Form.Item>
                <Form.Item name="description" label="说明">
                    <Input.TextArea
                        autoSize={{ minRows: 2, maxRows: 4 }}
                        placeholder={isProtected ? '内置角色的说明建议保留' : '描述该角色的用途'}
                    />
                </Form.Item>
                <Form.Item
                    name="permission_tags"
                    label="权限标签"
                    tooltip={
                        isProtected
                            ? '内置角色的权限标签建议谨慎修改'
                            : '持有任一相同标签的用户即可访问该标签下的文档'
                    }
                >
                    <PermissionTagsField placeholder="输入标签后回车" />
                </Form.Item>
            </Form>
        </Modal>
    )
}