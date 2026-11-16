import { AimOutlined } from '@ant-design/icons'
import { App, Button, Form, Input, Modal, Select, Space, Typography } from 'antd'
import { useState } from 'react'
import type { Location } from '../../api/types'
import { PlaceMap, type LatLng } from '../../components/PlaceMap'
import { COUNTRY_OPTIONS } from '../../utils/countries'

interface Props {
  open: boolean
  value: Location | null
  onCancel: () => void
  onSave: (loc: Location | null) => void
}

interface FormValues {
  place_name: string
  country_code?: string
}

/** Render only while open so state initialises from `value` each time. */
export function LocationModal({ open, value, onCancel, onSave }: Props) {
  const { message } = App.useApp()
  const [form] = Form.useForm<FormValues>()
  const [point, setPoint] = useState<LatLng | null>(value ? { lat: value.lat, lng: value.lng } : null)
  const [locating, setLocating] = useState(false)

  const useMyLocation = () => {
    if (!navigator.geolocation) {
      message.error('Your browser does not support location')
      return
    }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setPoint({ lat: pos.coords.latitude, lng: pos.coords.longitude })
        setLocating(false)
      },
      () => {
        message.error('Could not get your location')
        setLocating(false)
      },
      { enableHighAccuracy: false, timeout: 10_000 },
    )
  }

  const submit = (v: FormValues) => {
    if (!point) {
      message.warning('Click the map to drop a pin')
      return
    }
    onSave({
      place_name: v.place_name.trim(),
      country_code: v.country_code ?? null,
      lat: Number(point.lat.toFixed(6)),
      lng: Number((((point.lng + 540) % 360) - 180).toFixed(6)), // wrap to [-180, 180)
    })
  }

  return (
    <Modal
      title="Where was this?"
      open={open}
      onCancel={onCancel}
      width={640}
      destroyOnHidden
      footer={
        <Space>
          {value && (
            <Button danger onClick={() => onSave(null)}>
              Remove location
            </Button>
          )}
          <Button onClick={onCancel}>Cancel</Button>
          <Button type="primary" onClick={() => form.submit()}>
            Save location
          </Button>
        </Space>
      }
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={submit}
        requiredMark={false}
        initialValues={{ place_name: value?.place_name ?? '', country_code: value?.country_code ?? undefined }}
      >
        <Form.Item
          name="place_name"
          label="Place"
          rules={[{ required: true, whitespace: true, message: 'Name the place' }]}
        >
          <Input placeholder="e.g. Cusco, Peru" maxLength={200} />
        </Form.Item>
        <Form.Item name="country_code" label="Country">
          <Select
            showSearch
            allowClear
            placeholder="Select a country"
            options={COUNTRY_OPTIONS}
            optionFilterProp="name"
          />
        </Form.Item>
      </Form>
      <Space style={{ marginBottom: 8, justifyContent: 'space-between', width: '100%' }}>
        <Typography.Text type="secondary">Click the map to drop a pin.</Typography.Text>
        <Button size="small" icon={<AimOutlined />} onClick={useMyLocation} loading={locating}>
          Use my location
        </Button>
      </Space>
      <PlaceMap point={point} onPick={setPoint} height={320} />
    </Modal>
  )
}
