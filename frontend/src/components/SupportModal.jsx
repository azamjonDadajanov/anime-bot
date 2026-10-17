import { useState } from 'react'
import { Alert, Button, Group, Modal, Stack, Text, Textarea } from '@mantine/core'
import { supportApi } from '../apis/api'

const MAX_LENGTH = 2000

function errorText(error) {
  const data = error.response?.data
  if (!data) return "Server bilan bog'lanishda xatolik yuz berdi."
  if (typeof data.detail === 'string') return data.detail
  const first = Object.values(data).flat().map(String)[0]
  return first || "Xabar yuborilmadi."
}

function SupportModal({ opened, onClose }) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  function handleClose() {
    if (sending) return
    setText('')
    setMessage('')
    setError('')
    onClose()
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const body = text.trim()
    if (!body) {
      setError('Xabar matnini kiriting.')
      return
    }
    setSending(true)
    setMessage('')
    setError('')
    try {
      const data = await supportApi.send(body)
      setText('')
      if (data.delivered) {
        setMessage(data.detail || 'Xabaringiz administratorlarga yuborildi.')
      } else {
        setError(data.detail || "Xabar saqlandi, lekin hozircha yuborilmadi.")
      }
    } catch (requestError) {
      setError(errorText(requestError))
    } finally {
      setSending(false)
    }
  }

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      centered
      radius="lg"
      title="Adminga xabar"
      classNames={{ body: 'support-modal-body' }}
    >
      <form onSubmit={handleSubmit}>
        <Stack gap="sm">
          <Text size="sm" c="dimmed">
            Savol, taklif yoki muammoingizni yozing — xabar barcha administratorlarga yetib boradi.
          </Text>

          {message && <Alert color="green">{message}</Alert>}
          {error && <Alert color="red">{error}</Alert>}

          <Textarea
            label="Xabar matni"
            placeholder="Masalan: obuna to'lovim tasdiqlanmadi..."
            autosize
            minRows={4}
            maxRows={10}
            maxLength={MAX_LENGTH}
            required
            value={text}
            onChange={(event) => setText(event.currentTarget.value)}
            disabled={sending}
          />

          <Group justify="space-between" align="center">
            <Text size="xs" c="dimmed">
              {text.length}/{MAX_LENGTH}
            </Text>
            <Group gap="xs">
              <Button variant="subtle" color="gray" onClick={handleClose} disabled={sending}>
                Yopish
              </Button>
              <Button
                type="submit"
                loading={sending}
                disabled={!text.trim()}
                leftSection={<i className="bi bi-send" aria-hidden="true" />}
              >
                Yuborish
              </Button>
            </Group>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

export default SupportModal
