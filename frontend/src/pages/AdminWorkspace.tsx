import { useEffect, useMemo, useState, type FormEvent } from 'react'

import { api, jsonBody } from '../lib/api'

type FieldKind = 'text' | 'date' | 'number' | 'boolean'
interface FieldDefinition {
  key: string
  label: string
  kind?: FieldKind
  required?: boolean
}
interface ResourceDefinition {
  key: string
  label: string
  fields: FieldDefinition[]
}
type AdminArea = 'academic' | 'faculty' | 'students'

const academicResources: ResourceDefinition[] = [
  {
    key: 'academic-years',
    label: 'Academic years',
    fields: [
      { key: 'name', label: 'Name', required: true },
      { key: 'start_date', label: 'Start date', kind: 'date', required: true },
      { key: 'end_date', label: 'End date', kind: 'date', required: true },
      { key: 'is_current', label: 'Current year', kind: 'boolean' },
    ],
  },
  {
    key: 'departments',
    label: 'Departments',
    fields: [
      { key: 'name', label: 'Name', required: true },
      { key: 'code', label: 'Code', required: true },
    ],
  },
  {
    key: 'branches',
    label: 'Branches',
    fields: [
      { key: 'department_id', label: 'Department ID', required: true },
      { key: 'name', label: 'Name', required: true },
      { key: 'code', label: 'Code', required: true },
    ],
  },
  {
    key: 'classes',
    label: 'Classes / sections',
    fields: [
      { key: 'branch_id', label: 'Branch ID', required: true },
      { key: 'academic_year_id', label: 'Academic year ID', required: true },
      { key: 'year_of_study', label: 'Year of study', kind: 'number', required: true },
      { key: 'semester', label: 'Semester', kind: 'number', required: true },
      { key: 'section', label: 'Section', required: true },
    ],
  },
  {
    key: 'subjects',
    label: 'Subjects',
    fields: [
      { key: 'department_id', label: 'Department ID', required: true },
      { key: 'name', label: 'Name', required: true },
      { key: 'code', label: 'Code', required: true },
    ],
  },
  {
    key: 'faculty-assignments',
    label: 'Faculty assignments',
    fields: [
      { key: 'faculty_user_id', label: 'Faculty user ID', required: true },
      { key: 'subject_id', label: 'Subject ID', required: true },
      { key: 'class_id', label: 'Class ID', required: true },
      { key: 'academic_year_id', label: 'Academic year ID', required: true },
    ],
  },
  {
    key: 'enrollments',
    label: 'Student enrollments',
    fields: [
      { key: 'student_user_id', label: 'Student user ID', required: true },
      { key: 'class_id', label: 'Class ID', required: true },
      { key: 'academic_year_id', label: 'Academic year ID', required: true },
      { key: 'enrollment_type', label: 'Enrollment type' },
    ],
  },
]

const accountFields: Record<'faculty' | 'students', FieldDefinition[]> = {
  faculty: [
    { key: 'email', label: 'Email', required: true },
    { key: 'password', label: 'Temporary password (12+ characters)', required: true },
    { key: 'first_name', label: 'First name', required: true },
    { key: 'last_name', label: 'Last name', required: true },
    { key: 'employee_id', label: 'Employee ID', required: true },
    { key: 'department_id', label: 'Department ID', required: true },
    { key: 'designation', label: 'Designation' },
  ],
  students: [
    { key: 'email', label: 'Email', required: true },
    { key: 'password', label: 'Temporary password (12+ characters)', required: true },
    { key: 'first_name', label: 'First name', required: true },
    { key: 'last_name', label: 'Last name', required: true },
    { key: 'roll_number', label: 'Roll number', required: true },
    { key: 'registration_number', label: 'Registration number' },
  ],
}

export function AdminWorkspace() {
  const [area, setArea] = useState<AdminArea>('academic')
  const [resourceKey, setResourceKey] = useState(academicResources[0].key)
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([])
  const [editing, setEditing] = useState<Record<string, unknown> | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const resource = useMemo(
    () => academicResources.find((item) => item.key === resourceKey) ?? academicResources[0],
    [resourceKey],
  )

  async function loadRows(selectedArea = area, selectedResource = resourceKey) {
    setError('')
    const path =
      selectedArea === 'academic'
        ? `/admin/academic/${selectedResource}`
        : `/admin/${selectedArea}`
    setRows(await api<Array<Record<string, unknown>>>(path))
  }

  useEffect(() => {
    void loadRows().catch((reason: unknown) =>
      setError(reason instanceof Error ? reason.message : 'Could not load records'),
    )
  }, [area, resourceKey])

  function changeArea(nextArea: AdminArea) {
    setArea(nextArea)
    setEditing(null)
    if (nextArea === 'academic' && !academicResources.some((item) => item.key === resourceKey)) {
      setResourceKey(academicResources[0].key)
    }
  }

  function fieldsForArea(): FieldDefinition[] {
    return area === 'academic' ? resource.fields : accountFields[area]
  }

  async function saveRecord(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const formElement = event.currentTarget
    const form = new FormData(formElement)
    const fields = fieldsForArea()
    const payload: Record<string, unknown> = {}
    for (const field of fields) {
      const value = form.get(field.key)
      if (field.kind === 'boolean') payload[field.key] = value === 'on'
      else if (field.kind === 'number') payload[field.key] = Number(value)
      else if (value !== null && String(value) !== '') payload[field.key] = String(value)
    }

    setBusy(true)
    setMessage('')
    setError('')
    try {
      if (editing) {
        const id = String(editing.id ?? editing.user_id ?? '')
        const path =
          area === 'academic'
            ? `/admin/academic/${resourceKey}/${id}`
            : `/admin/${area}/${id}`
        await api(path, { method: 'PATCH', body: jsonBody(payload) })
        setMessage('Record updated')
      } else {
        const path =
          area === 'academic'
            ? `/admin/academic/${resourceKey}`
            : `/admin/${area}`
        await api(path, { method: 'POST', body: jsonBody(payload) })
        setMessage(area === 'academic' ? 'Academic record created' : 'Account created')
      }
      setEditing(null)
      formElement.reset()
      await loadRows()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not save this record')
    } finally {
      setBusy(false)
    }
  }

  async function deactivate(row: Record<string, unknown>) {
    const id = String(row.id ?? row.user_id ?? '')
    if (!id || !window.confirm('Deactivate this record? Its history will be preserved.')) return
    const path =
      area === 'academic'
        ? `/admin/academic/${resourceKey}/${id}`
        : `/admin/${area}/${id}`
    setBusy(true)
    setError('')
    try {
      await api(path, { method: 'DELETE' })
      setMessage('Record deactivated')
      await loadRows()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not deactivate this record')
    } finally {
      setBusy(false)
    }
  }

  function editRecord(row: Record<string, unknown>) {
    setEditing(row)
    window.setTimeout(() => {
      const form = document.getElementById('admin-record-form') as HTMLFormElement | null
      if (!form) return
      for (const field of fieldsForArea()) {
        const input = form.elements.namedItem(field.key)
        if (input instanceof HTMLInputElement) {
          if (field.kind === 'boolean') input.checked = Boolean(row[field.key])
          else input.value = String(row[field.key] ?? '')
        } else if (input instanceof HTMLSelectElement || input instanceof HTMLTextAreaElement) {
          input.value = String(row[field.key] ?? '')
        }
      }
    }, 0)
  }

  function displayValue(value: unknown): string {
    if (value === null || value === undefined) return '—'
    if (typeof value === 'boolean') return value ? 'Yes' : 'No'
    if (typeof value === 'object') return JSON.stringify(value)
    return String(value)
  }

  const columns = rows.length
    ? Object.keys(rows[0]).filter((key) => !['updated_at', 'created_at'].includes(key)).slice(0, 6)
    : []

  return (
    <div className="page-stack">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">Administration</p>
          <h1>Academic operations</h1>
          <p className="muted">Manage real college records. Changes are saved through the protected API.</p>
        </div>
        <div className="hero-stat"><span>{rows.length}</span><small>records shown</small></div>
      </section>
      {(message || error) && (
        <p className={`notice ${error ? 'notice-error' : 'notice-success'}`}>{error || message}</p>
      )}
      <div className="admin-tabs" role="tablist" aria-label="Administration area">
        {([
          ['academic', 'Academic structure'],
          ['faculty', 'Faculty'],
          ['students', 'Students'],
        ] as const).map(([key, label]) => (
          <button
            className={`tab-button ${area === key ? 'tab-active' : ''}`}
            key={key}
            onClick={() => changeArea(key)}
            role="tab"
            aria-selected={area === key}
          >
            {label}
          </button>
        ))}
      </div>
      <section className="two-column admin-layout">
        <div className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">{area === 'academic' ? 'Academic records' : 'Account directory'}</p>
              <h2>{editing ? 'Edit record' : 'Create record'}</h2>
            </div>
            {editing && <button className="button button-quiet" onClick={() => setEditing(null)}>Cancel</button>}
          </div>
          {area === 'academic' && (
            <label className="resource-picker">
              Record type
              <select value={resourceKey} onChange={(event) => setResourceKey(event.target.value)}>
                {academicResources.map((item) => (
                  <option value={item.key} key={item.key}>{item.label}</option>
                ))}
              </select>
            </label>
          )}
          <form id="admin-record-form" className="form-stack compact-form" onSubmit={saveRecord}>
            {fieldsForArea().map((field) => (
              <label className={field.kind === 'boolean' ? 'checkbox-label' : ''} key={field.key}>
                {field.kind === 'boolean' ? (
                  <>
                    <input type="checkbox" name={field.key} defaultChecked={Boolean(editing?.[field.key])} />
                    {field.label}
                  </>
                ) : (
                  <>
                    {field.label}
                    <input
                      name={field.key}
                      required={!editing && (field.required ?? true)}
                      type={field.kind === 'date' ? 'date' : field.kind === 'number' ? 'number' : 'text'}
                      defaultValue={
                        field.key === 'enrollment_type'
                          ? 'CORE'
                          : String(editing?.[field.key] ?? '')
                      }
                    />
                  </>
                )}
              </label>
            ))}
            <button className="button button-primary" disabled={busy}>
              {busy ? 'Saving…' : editing ? 'Save changes' : 'Create'}
            </button>
            {area === 'students' && !editing && (
              <p className="helper-text">
                New students must be assigned to an academic class using the Enrollments section.
              </p>
            )}
          </form>
        </div>
        <div className="panel">
          <div className="section-heading">
            <div><p className="eyebrow">College data</p><h2>{area === 'academic' ? resource.label : area}</h2></div>
            <button className="button button-quiet" onClick={() => void loadRows()}>Refresh</button>
          </div>
          {rows.length === 0 ? (
            <div className="empty-state"><strong>No records found</strong><span>Add the first record using the form.</span></div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>{columns.map((column) => <th key={column}>{column.replaceAll('_', ' ')}</th>)}<th>Actions</th></tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr key={String(row.id ?? row.user_id ?? index)}>
                      {columns.map((column) => <td key={column}>{displayValue(row[column])}</td>)}
                      <td>
                        <div className="row-actions">
                          <button className="button button-small button-quiet" onClick={() => editRecord(row)}>Edit</button>
                          <button className="button button-small button-danger-quiet" disabled={busy} onClick={() => void deactivate(row)}>Deactivate</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
