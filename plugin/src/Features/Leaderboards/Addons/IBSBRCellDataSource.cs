namespace BSBRLeaderboard.Features.Leaderboards.Addons {

    /// <summary>Fonte de dados de uma célula do leaderboard customizado (port do ICellDataSource do AccSaber).</summary>
    internal interface IBSBRCellDataSource {
        /// <summary>Nome do recurso .bsml embutido (LogicalName = FullName.bsml) que é o template da célula.</summary>
        string TemplatePath { get; }
        /// <summary>Altura da célula em unidades BSML.</summary>
        float CellSize { get; }
        /// <summary>Id interno do template (setado pelo BSBRCellListTableData ao agrupar por TemplatePath).</summary>
        int TemplateId { get; set; }
    }
}
