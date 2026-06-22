Attribute VB_Name = "CardLifecycle"
'======================================================================
' Card Lifecycle Management — VBA automation (OPTIONAL layer)
'----------------------------------------------------------------------
' The workbook works WITHOUT macros: Card Age, Age Category, the
' Destruction Flag, the KPIs, the conditional formatting and the
' Destruction Due Report are all live Excel formulas.
'
' This module adds the parts the spec marks as automation:
'   * Audit logging of 60 / 85 / 90-day transitions (Audit_Log sheet)
'   * "Mark for Destruction" action with audit trail
'   * A pop-up alert when red (90+) cards exceed the threshold
'
' INSTALL
'   1. Open CardLifecycle.xlsx in Excel.
'   2. Alt+F11 -> File -> Import File... -> select this .bas
'   3. Paste the ThisWorkbook snippet (bottom of this file) into the
'      "ThisWorkbook" object so RefreshLifecycle runs on open.
'   4. Save As -> Excel Macro-Enabled Workbook (*.xlsm).
'======================================================================
Option Explicit

Private Const SHEET_MASTER As String = "Card_Master"
Private Const SHEET_AUDIT As String = "Audit_Log"
Private Const COL_LAST_STATUS As Long = 12   ' column L: last audited status (helper)

'--- Read business constants from the Config named ranges --------------
Private Function WarningDays() As Long: WarningDays = Range("WarningDays").Value: End Function
Private Function EscalateDays() As Long: EscalateDays = Range("EscalateDays").Value: End Function
Private Function DestructionDays() As Long: DestructionDays = Range("DestructionDays").Value: End Function
Private Function RedAlertThreshold() As Long: RedAlertThreshold = Range("RedAlertThreshold").Value: End Function

'======================================================================
' Master refresh — recalculates ages and logs any status transitions.
' Safe to run as often as you like (idempotent: only NEW transitions
' are written to the audit log).
'======================================================================
Public Sub RefreshLifecycle()
    Dim ws As Worksheet, lo As ListObject
    Dim r As Long, lastRow As Long
    Dim age As Variant, curStatus As String, prevStatus As String
    Dim cardNo As String

    Application.CalculateFull
    Set ws = ThisWorkbook.Worksheets(SHEET_MASTER)
    Set lo = ws.ListObjects("Card_Master")

    ' Ensure helper header exists (kept just to the right of the table).
    If Trim(ws.Cells(1, COL_LAST_STATUS).Value) = "" Then
        ws.Cells(1, COL_LAST_STATUS).Value = "Last Audited Status"
    End If

    lastRow = lo.ListRows.Count + lo.HeaderRowRange.Row
    For r = lo.HeaderRowRange.Row + 1 To lastRow
        cardNo = CStr(ws.Cells(r, 1).Value)
        If cardNo = "" Then GoTo NextRow
        age = ws.Cells(r, 6).Value           ' column F: Card Age (Days)
        If Not IsNumeric(age) Then GoTo NextRow

        curStatus = StatusFor(CLng(age))
        prevStatus = CStr(ws.Cells(r, COL_LAST_STATUS).Value)

        If curStatus <> prevStatus Then
            ' Only audit meaningful, loggable transitions.
            Select Case curStatus
                Case "Warning"
                    LogAudit cardNo, "Crossed " & WarningDays & " days", _
                             prevStatus, curStatus, CLng(age), _
                             "Early-warning flag raised"
                Case "Warning (High Risk)"
                    LogAudit cardNo, "Crossed " & EscalateDays & " days", _
                             prevStatus, curStatus, CLng(age), _
                             "Escalation — high risk"
                Case "Due for Destruction"
                    LogAudit cardNo, "Crossed " & DestructionDays & " days", _
                             prevStatus, curStatus, CLng(age), _
                             "Eligible for destruction"
            End Select
            ws.Cells(r, COL_LAST_STATUS).Value = curStatus
        End If
NextRow:
    Next r

    AlertIfBacklog
End Sub

'--- Status (incl. the 85-day high-risk sub-band) ---------------------
Private Function StatusFor(ByVal age As Long) As String
    If age >= DestructionDays Then
        StatusFor = "Due for Destruction"
    ElseIf age >= EscalateDays Then
        StatusFor = "Warning (High Risk)"
    ElseIf age >= WarningDays Then
        StatusFor = "Warning"
    Else
        StatusFor = "Normal"
    End If
End Function

'======================================================================
' Mark the card under the active cell (on Card_Master) as physically
' destroyed — records an audit entry. Use after operational destruction.
'======================================================================
Public Sub MarkForDestruction()
    Dim ws As Worksheet, r As Long, age As Variant, cardNo As String
    Set ws = ThisWorkbook.Worksheets(SHEET_MASTER)
    If ActiveSheet.Name <> SHEET_MASTER Then
        MsgBox "Select a card row on the Card_Master sheet first.", vbExclamation
        Exit Sub
    End If
    r = ActiveCell.Row
    cardNo = CStr(ws.Cells(r, 1).Value)
    age = ws.Cells(r, 6).Value
    If cardNo = "" Then Exit Sub
    If Not IsNumeric(age) Or CLng(age) < DestructionDays Then
        If MsgBox("Card " & cardNo & " is not yet 90 days old. Mark anyway?", _
                  vbYesNo + vbQuestion) = vbNo Then Exit Sub
    End If
    LogAudit cardNo, "Marked for destruction", _
             CStr(ws.Cells(r, 7).Value), "Destroyed", _
             IIf(IsNumeric(age), CLng(age), 0), _
             "Operator: " & Environ$("USERNAME")
    MsgBox "Logged destruction of card " & cardNo & ".", vbInformation
End Sub

'======================================================================
' Pop-up alert (in addition to the dashboard banner) when the red
' backlog exceeds the configured threshold.
'======================================================================
Public Sub AlertIfBacklog()
    Dim n As Long
    n = Application.WorksheetFunction.CountIf( _
            ThisWorkbook.Worksheets(SHEET_MASTER).ListObjects("Card_Master") _
                .ListColumns("Card Age (Days)").DataBodyRange, ">=" & DestructionDays)
    If n > RedAlertThreshold Then
        MsgBox "ALERT: " & n & " cards are DUE FOR DESTRUCTION " & _
               "(threshold " & RedAlertThreshold & ")." & vbCrLf & _
               "See the Destruction_Due_Report sheet.", _
               vbCritical, "Card Lifecycle — Destruction Backlog"
    End If
End Sub

'--- Append one immutable row to the Audit_Log ------------------------
Private Sub LogAudit(ByVal cardNo As String, ByVal evt As String, _
                     ByVal oldStatus As String, ByVal newStatus As String, _
                     ByVal age As Long, ByVal notes As String)
    Dim al As Worksheet, nextRow As Long
    Set al = ThisWorkbook.Worksheets(SHEET_AUDIT)
    nextRow = al.Cells(al.Rows.Count, 1).End(xlUp).Row + 1
    If nextRow < 4 Then nextRow = 4
    al.Cells(nextRow, 1).Value = Now
    al.Cells(nextRow, 1).NumberFormat = "yyyy-mm-dd hh:mm"
    al.Cells(nextRow, 2).Value = cardNo
    al.Cells(nextRow, 3).Value = evt
    al.Cells(nextRow, 4).Value = oldStatus
    al.Cells(nextRow, 5).Value = newStatus
    al.Cells(nextRow, 6).Value = age
    al.Cells(nextRow, 7).Value = "SYSTEM"
    al.Cells(nextRow, 8).Value = notes
End Sub

'======================================================================
' Paste THIS into the "ThisWorkbook" object (not a standard module):
'
'   Private Sub Workbook_Open()
'       CardLifecycle.RefreshLifecycle
'   End Sub
'
'======================================================================
