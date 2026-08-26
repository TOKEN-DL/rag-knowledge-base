import { Select } from 'antd'
interface PermissionTagsFieldProps {
    value?: string[]
    onChange?: (value: string[]) => void
    placeholder?: string
    disabled?: boolean
}


export function PermissionTagsField({
    value, onChange,
    placeholder = '输入标签后回车，留空视为公开',
    disabled,
}: PermissionTagsFieldProps) {
    return (
        <Select
            mode="tags"
            tokenSeparators={[',', ' ']}
            placeholder={placeholder}
            value={value}
            onChange={onChange}
            disabled={disabled}
            style={{ width: '100%' }}
        />
    )
}