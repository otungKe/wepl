Attribute VB_Name = "CardOps_Dashboard"
'======================================================================
' CARD OPERATIONS — CONTROL CENTRE  (application-grade dashboard)
'----------------------------------------------------------------------
' Builds a live dashboard for the I&M card register that mirrors the
' three-stage cycle:
'     (1) RECORD     - a card is logged on arrival          -> RecordNewCard
'     (2) LIFECYCLE  - Days in Branch ages it (90-day rule) -> live formulas
'     (3) REMIND     - collection / destruction reminders   -> your existing
'                      SendCardEmails / GenerateDestructionRegister macros
'
' SAFE BY DESIGN: it only adds/refreshes a sheet called "Dashboard".
' It does NOT touch "Dashboard_2026", the Card Register data, the Status
' dropdown, your conditional formatting, the checkboxes, or any of your
' other macros.
'
' INSTALL
'   1. Open the register (.xlsm), Alt+F11, File > Import File... > this .bas
'   2. Back in Excel: Developer > Macros > BuildDashboard > Run
'      (or just press the buttons it creates afterwards).
'======================================================================
Option Explicit

' ---- business rule ----
Private Const EARLY As Long = 30
Private Const WARN As Long = 60
Private Const DUE As Long = 90
Private Const GAP As Long = 7          ' anti-spam days between reminders
Private Const RED_ALERT As Long = 5    ' banner threshold

' ---- palette (RGB) ----
Private Function cBRAND() As Long: cBRAND = RGB(27, 94, 32): End Function
Private Function cBAND() As Long: cBAND = RGB(11, 61, 23): End Function
Private Function cGOLD() As Long: cGOLD = RGB(200, 160, 66): End Function
Private Function cPAPER() As Long: cPAPER = RGB(244, 246, 244): End Function
Private Function cINK() As Long: cINK = RGB(14, 42, 30): End Function
Private Function cMUTE() As Long: cMUTE = RGB(138, 147, 140): End Function
Private Function cGREEN() As Long: cGREEN = RGB(46, 125, 50): End Function
Private Function cAMBER() As Long: cAMBER = RGB(243, 156, 18): End Function
Private Function cRED() As Long: cRED = RGB(192, 57, 43): End Function
Private Function cBLUE() As Long: cBLUE = RGB(47, 109, 181): End Function
Private Function cGREY() As Long: cGREY = RGB(91, 107, 97): End Function

Private Const SRC As String = "Card Register"

'======================================================================
Public Sub BuildDashboard()
    Dim ws As Worksheet, src As Worksheet
    Application.ScreenUpdating = False
    Application.DisplayAlerts = False

    Set src = SheetByName(SRC)
    If src Is Nothing Then
        MsgBox "Sheet '" & SRC & "' not found.", vbExclamation: Exit Sub
    End If

    ' fresh Dashboard sheet (leaves Dashboard_2026 untouched)
    On Error Resume Next
    ThisWorkbook.Worksheets("Dashboard").Delete
    On Error GoTo 0
    Set ws = ThisWorkbook.Worksheets.Add(Before:=ThisWorkbook.Worksheets(1))
    ws.Name = "Dashboard"
    ws.Tab.Color = cBRAND
    ws.Cells.Interior.Color = cPAPER
    ws.DisplayGridlines = False: ws.Cells.Font.Name = "Segoe UI"

    Dim c As Long, lastG As String
    lastG = "'" & SRC & "'!$G$2:$G$100000"
    Dim H As String: H = "'" & SRC & "'!$H$2:$H$100000"
    Dim Gr As String: Gr = lastG

    ' grid
    For c = 1 To 21: ws.Columns(c).ColumnWidth = 9.5: Next c
    ws.Columns(1).ColumnWidth = 2.5: ws.Columns(22).ColumnWidth = 2.5

    BuildHelpers ws, src   ' hidden chart-source tables (cols AA+)

    ' ----- hero -----
    With ws.Range("B2:T4")
        .Merge: .Interior.Color = cBAND
        .Value = "  CARD OPERATIONS — CONTROL CENTRE"
        .Font.Size = 22: .Font.Bold = True: .Font.Color = vbWhite
        .HorizontalAlignment = xlLeft: .VerticalAlignment = xlCenter
    End With
    With ws.Range("P2:T4")
        .Merge: .Interior.Color = cBAND
        .Value = Format(Date, "dddd, dd mmm yyyy")
        .Font.Italic = True: .Font.Color = cGOLD: .Font.Size = 11
        .HorizontalAlignment = xlRight: .VerticalAlignment = xlCenter
    End With
    ws.Rows(2).RowHeight = 14: ws.Rows(3).RowHeight = 26: ws.Rows(4).RowHeight = 14

    ' ----- alert ribbon -----
    Dim heldDue As String
    heldDue = "COUNTIFS(" & H & ",""Held""," & Gr & ","">=""&" & DUE & ")"
    With ws.Range("B5:T5")
        .Merge
        .Formula = "=IF(" & heldDue & ">" & RED_ALERT & ",""! ""&" & heldDue & _
            "&"" held cards DUE FOR DESTRUCTION. Generate the Destruction Register + final notices.""," & _
            """OK  Destruction backlog under control - ""&" & heldDue & "&"" card(s) at/over 90 days."")"
        .HorizontalAlignment = xlLeft: .VerticalAlignment = xlCenter
        .Font.Bold = True
    End With
    ws.Rows(5).RowHeight = 22
    AddFCRule ws.Range("B5"), "=" & heldDue & ">" & RED_ALERT, cRED, vbWhite
    AddFCRule ws.Range("B5"), "=" & heldDue & "<=" & RED_ALERT, RGB(230, 244, 234), cGREEN

    ' ----- cycle pipeline -----
    SectionTitle ws, "B7", "THE CARD CYCLE"
    PipeTile ws, 2, "1  RECORD", "Logged on arrival", "=COUNTA('" & SRC & "'!$C$2:$C$100000)", cBLUE
    PipeTile ws, 9, "2  LIFECYCLE", "In branch, ageing", "=COUNTIF(" & H & ",""Held*"")", cAMBER
    PipeTile ws, 16, "3  REMIND", "Reminders due now", "=COUNTIFS(" & H & ",""Held""," & Gr & ","">=""&" & EARLY & ")", cGREEN

    ' ----- KPI tiles -----
    SectionTitle ws, "B12", "KEY METRICS"
    KpiTile ws, 2, "TOTAL CARDS", "=COUNTA('" & SRC & "'!$C$2:$C$100000)", cINK
    KpiTile ws, 5, "IN BRANCH", "=COUNTIF(" & H & ",""Held*"")", cBLUE
    KpiTile ws, 8, "COLLECTED", "=COUNTIF(" & H & ",""Issued*"")", cGREEN
    KpiTile ws, 11, "DESTROYED", "=COUNTIF(" & H & ",""Destroyed*"")", cGREY
    KpiTile ws, 14, "DUE FOR DESTRUCTION", "=" & heldDue, cRED
    KpiTile ws, 17, "WARNING 60-89", "=COUNTIFS(" & H & ",""Held""," & Gr & ","">=""&" & WARN & "," & Gr & ",""<""&" & DUE & ")", cAMBER

    ' ----- charts -----
    SectionTitle ws, "B18", "PORTFOLIO STATUS"
    SectionTitle ws, "J18", "AGEING DISTRIBUTION (days in branch)"
    SectionTitle ws, "B33", "RECORDING TREND - cards per month"
    SectionTitle ws, "J33", "BRANCH HEALTH (share by age band)"
    MakeDonut ws
    MakeAgingCol ws
    MakeTrendLine ws
    MakeHealthBar ws

    ' ----- action buttons -----
    SectionTitle ws, "B46", "ACTIONS"
    AddButton ws, "C47", "+ Record New Card", "RecordNewCard", cBRAND
    AddButton ws, "G47", "Send Reminders", "SendCardEmails", cBLUE
    AddButton ws, "K47", "Destruction Register", "GenerateDestructionRegister", cRED
    AddButton ws, "O47", "Refresh", "BuildDashboard", cGREY

    ' footer
    With ws.Range("B58:T58")
        .Merge: .Value = "Live - ageing = TODAY() - Date Received - thresholds in code - " & _
            "reminders/destruction via SendCardEmails & GenerateDestructionRegister."
        .Font.Italic = True: .Font.Size = 8.5: .Font.Color = cMUTE
    End With

    ws.Range("A1").Select
    Application.ScreenUpdating = True
    Application.DisplayAlerts = True
    MsgBox "Dashboard built. Use the buttons to run the cycle.", vbInformation
End Sub

'======================================================================
' STAGE 1 - record a card on arrival (appends a Held row, dated today)
'======================================================================
Public Sub RecordNewCard()
    Dim src As Worksheet, r As Long
    Dim nm As String, card As String, phone As String, email As String
    Set src = SheetByName(SRC)
    If src Is Nothing Then Exit Sub

    nm = Trim(InputBox("Customer name:", "Record New Card"))
    If nm = "" Then Exit Sub
    card = Trim(InputBox("Card number:", "Record New Card"))
    If card = "" Then Exit Sub
    phone = Trim(InputBox("Phone number:", "Record New Card"))
    email = Trim(InputBox("Email address:", "Record New Card"))

    r = src.Cells(src.Rows.Count, "A").End(xlUp).Row + 1
    src.Cells(r, "A").Value = Date
    src.Cells(r, "A").NumberFormat = "yyyy-mm-dd"
    src.Cells(r, "B").Value = nm
    src.Cells(r, "C").Value = card
    src.Cells(r, "E").Value = phone
    src.Cells(r, "F").Value = email
    ' G (Days in Branch) keeps the sheet's own formula if present; else set it
    If Len(src.Cells(r, "G").Formula) = 0 Then
        src.Cells(r, "G").Formula = "=IF(I" & r & "="""",TODAY()-A" & r & ",I" & r & "-A" & r & ")"
    End If
    src.Cells(r, "H").Value = "Held"
    MsgBox "Recorded '" & nm & "' as HELD (arrived " & Format(Date, "dd-mmm-yyyy") & ").", vbInformation
    On Error Resume Next
    BuildDashboard
End Sub

'======================== helpers =====================================
Private Sub BuildHelpers(ws As Worksheet, src As Worksheet)
    Dim H As String, G As String, A As String
    H = "'" & SRC & "'!$H$2:$H$100000"
    G = "'" & SRC & "'!$G$2:$G$100000"
    A = "'" & SRC & "'!$A$2:$A$100000"

    ' status table  AB1:AC5
    ws.Range("AB1").Value = "Status": ws.Range("AC1").Value = "Cards"
    ws.Range("AB2").Value = "In Branch": ws.Range("AC2").Formula = "=COUNTIF(" & H & ",""Held*"")"
    ws.Range("AB3").Value = "Collected": ws.Range("AC3").Formula = "=COUNTIF(" & H & ",""Issued*"")"
    ws.Range("AB4").Value = "Destroyed": ws.Range("AC4").Formula = "=COUNTIF(" & H & ",""Destroyed*"")"
    ws.Range("AB5").Value = "Pending": ws.Range("AC5").Formula = "=COUNTIF(" & H & ",""Pend*"")"

    ' aging table  AE1:AF5
    ws.Range("AE1").Value = "Band": ws.Range("AF1").Value = "Cards"
    ws.Range("AE2").Value = "New 0-29": ws.Range("AF2").Formula = "=COUNTIFS(" & G & ","">=0""," & G & ",""<""&" & EARLY & ")"
    ws.Range("AE3").Value = "Normal 30-59": ws.Range("AF3").Formula = "=COUNTIFS(" & G & ","">=""&" & EARLY & "," & G & ",""<""&" & WARN & ")"
    ws.Range("AE4").Value = "Warning 60-89": ws.Range("AF4").Formula = "=COUNTIFS(" & G & ","">=""&" & WARN & "," & G & ",""<""&" & DUE & ")"
    ws.Range("AE5").Value = "Due 90+": ws.Range("AF5").Formula = "=COUNTIFS(" & G & ","">=""&" & DUE & ")"

    ' month table  AH1:AI13 (current year)
    Dim m As Long, yr As Long: yr = Year(Date)
    ws.Range("AH1").Value = "Month": ws.Range("AI1").Value = "Recorded"
    For m = 1 To 12
        ws.Cells(1 + m, 34).Value = DateSerial(yr, m, 1)
        ws.Cells(1 + m, 34).NumberFormat = "mmm"
        ws.Cells(1 + m, 35).Formula = "=COUNTIFS(" & A & ","">=""&DATE(" & yr & "," & m & ",1)," & _
            A & ",""<""&DATE(" & yr & "," & m + 1 & ",1))"
    Next m

    ' health (single 100% stacked)  AK1:AN2
    ws.Range("AK1").Value = "Seg": ws.Range("AL1").Value = "New": ws.Range("AM1").Value = "Normal"
    ws.Range("AN1").Value = "Warning": ws.Range("AO1").Value = "Due"
    ws.Range("AK2").Value = "Portfolio"
    ws.Range("AL2").Formula = "=AF2": ws.Range("AM2").Formula = "=AF3"
    ws.Range("AN2").Formula = "=AF4": ws.Range("AO2").Formula = "=AF5"

    ws.Columns("AA:AO").Hidden = True
End Sub

Private Sub MakeDonut(ws As Worksheet)
    Dim ch As Chart, i As Long
    Set ch = AddChart(ws, "B19", 175, 130)
    ch.ChartType = xlDoughnut
    ch.SetSourceData ws.Range("AB1:AC5")
    ch.HasTitle = False: ch.HasLegend = True: ch.Legend.Position = xlLegendPositionBottom
    Dim cols As Variant: cols = Array(cBLUE, cGREEN, cGREY, cAMBER)
    With ch.SeriesCollection(1)
        .DoughnutHoleSize = 62
        For i = 1 To 4
            .Points(i).Format.Fill.ForeColor.RGB = cols(i - 1)
        Next i
        .HasDataLabels = True: .DataLabels.ShowValue = True
    End With
End Sub

Private Sub MakeAgingCol(ws As Worksheet)
    Dim ch As Chart, i As Long
    Set ch = AddChart(ws, "J19", 360, 130)
    ch.ChartType = xlColumnClustered
    ch.SetSourceData ws.Range("AE1:AF5")
    ch.HasTitle = False: ch.HasLegend = False
    Dim cols As Variant: cols = Array(cGREEN, cBRAND, cAMBER, cRED)
    With ch.SeriesCollection(1)
        For i = 1 To 4
            .Points(i).Format.Fill.ForeColor.RGB = cols(i - 1)
        Next i
        .HasDataLabels = True
    End With
End Sub

Private Sub MakeTrendLine(ws As Worksheet)
    Dim ch As Chart
    Set ch = AddChart(ws, "B34", 360, 130)
    ch.ChartType = xlLine
    ch.SetSourceData ws.Range("AH1:AI13")
    ch.HasTitle = False: ch.HasLegend = False
    ch.SeriesCollection(1).Format.Line.ForeColor.RGB = cBRAND
    ch.SeriesCollection(1).Format.Line.Weight = 2.25
    ch.SeriesCollection(1).Smooth = True
End Sub

Private Sub MakeHealthBar(ws As Worksheet)
    Dim ch As Chart, i As Long
    Set ch = AddChart(ws, "J34", 360, 80)
    ch.ChartType = xlBarStacked100
    ch.SetSourceData ws.Range("AK1:AO2")
    ch.HasTitle = False: ch.HasLegend = True: ch.Legend.Position = xlLegendPositionBottom
    Dim cols As Variant: cols = Array(cGREEN, cBRAND, cAMBER, cRED)
    For i = 1 To 4
        ch.SeriesCollection(i).Format.Fill.ForeColor.RGB = cols(i - 1)
    Next i
End Sub

Private Function AddChart(ws As Worksheet, anchor As String, w As Single, h As Single) As Chart
    Dim co As ChartObject, rng As Range
    Set rng = ws.Range(anchor)
    Set co = ws.ChartObjects.Add(rng.Left, rng.Top, w, h)
    co.Chart.Parent.Format.Line.Visible = msoFalse
    Set AddChart = co.Chart
End Function

Private Sub KpiTile(ws As Worksheet, col As Long, label As String, formula As String, accent As Long)
    Dim top As Long: top = 13
    With ws.Range(ws.Cells(top, col), ws.Cells(top + 3, col + 2))
        .Interior.Color = vbWhite
    End With
    ws.Range(ws.Cells(top + 3, col), ws.Cells(top + 3, col + 2)).Borders(xlEdgeBottom).Weight = xlThick
    ws.Range(ws.Cells(top + 3, col), ws.Cells(top + 3, col + 2)).Borders(xlEdgeBottom).Color = accent
    With ws.Range(ws.Cells(top, col), ws.Cells(top, col + 2))
        .Merge: .Value = label: .Font.Bold = True: .Font.Size = 10: .Font.Color = cMUTE
        .HorizontalAlignment = xlLeft: .IndentLevel = 1
    End With
    With ws.Range(ws.Cells(top + 1, col), ws.Cells(top + 2, col + 2))
        .Merge: .Formula = formula: .Font.Bold = True: .Font.Size = 30: .Font.Color = accent
        .HorizontalAlignment = xlLeft: .VerticalAlignment = xlCenter: .IndentLevel = 1
    End With
    ws.Rows(top).RowHeight = 16: ws.Rows(top + 1).RowHeight = 22: ws.Rows(top + 2).RowHeight = 14
End Sub

Private Sub PipeTile(ws As Worksheet, col As Long, label As String, desc As String, formula As String, accent As Long)
    Dim c2 As Long: c2 = col + 5
    With ws.Range(ws.Cells(8, col), ws.Cells(10, c2))
        .Interior.Color = RGB(255, 255, 255)
    End With
    ws.Range(ws.Cells(8, col), ws.Cells(10, col)).Borders(xlEdgeLeft).Weight = xlThick
    ws.Range(ws.Cells(8, col), ws.Cells(10, col)).Borders(xlEdgeLeft).Color = accent
    With ws.Range(ws.Cells(8, col), ws.Cells(9, col + 3))
        .Merge: .Value = label: .Font.Bold = True: .Font.Size = 13: .Font.Color = accent
        .HorizontalAlignment = xlLeft: .VerticalAlignment = xlCenter: .IndentLevel = 1
    End With
    With ws.Range(ws.Cells(10, col), ws.Cells(10, col + 3))
        .Merge: .Value = desc: .Font.Italic = True: .Font.Size = 9: .Font.Color = cMUTE
        .HorizontalAlignment = xlLeft: .IndentLevel = 1
    End With
    With ws.Range(ws.Cells(8, col + 4), ws.Cells(10, c2))
        .Merge: .Formula = formula: .Font.Bold = True: .Font.Size = 24: .Font.Color = accent
        .HorizontalAlignment = xlRight: .VerticalAlignment = xlCenter: .IndentLevel = 1
    End With
End Sub

Private Sub SectionTitle(ws As Worksheet, addr As String, txt As String)
    With ws.Range(addr)
        .Value = txt: .Font.Bold = True: .Font.Size = 11: .Font.Color = cBRAND
    End With
End Sub

Private Sub AddButton(ws As Worksheet, anchor As String, caption As String, macro As String, clr As Long)
    Dim r As Range, shp As Shape
    Set r = ws.Range(anchor)
    Set shp = ws.Shapes.AddShape(msoShapeRoundedRectangle, r.Left, r.Top, 150, 26)
    shp.Fill.ForeColor.RGB = clr
    shp.Line.Visible = msoFalse
    shp.TextFrame2.TextRange.Text = caption
    shp.TextFrame2.TextRange.Font.Fill.ForeColor.RGB = vbWhite
    shp.TextFrame2.TextRange.Font.Size = 10
    shp.TextFrame2.TextRange.Font.Bold = msoTrue
    shp.TextFrame.HorizontalAlignment = xlHAlignCenter
    shp.OnAction = macro
End Sub

Private Sub AddFCRule(rng As Range, formula As String, bg As Long, fontClr As Long)
    Dim fc As FormatCondition
    Set fc = rng.FormatConditions.Add(Type:=xlExpression, Formula1:=formula)
    fc.Interior.Color = bg
    fc.Font.Color = fontClr
    fc.Font.Bold = True
End Sub

Private Function SheetByName(nm As String) As Worksheet
    On Error Resume Next
    Set SheetByName = ThisWorkbook.Worksheets(nm)
    On Error GoTo 0
End Function
