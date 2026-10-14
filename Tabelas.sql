/* =====================================================================
   ADS-5 - Script unico (Usuarios + Produtos + Livros + Emprestimos)
   Substitui Tabelas.sql e TabelasBiblioteca.sql.
   Pode ser executado varias vezes: NAO apaga dados existentes.
   Os usuarios iniciais (admin, professor, cliente) sao criados pela
   propria API na primeira execucao, ja com a senha em hash.
   ===================================================================== */
USE [master];
GO

IF DB_ID('ADS-5') IS NULL
BEGIN
    CREATE DATABASE [ADS-5];
END;
GO

USE [ADS-5];
GO

-- ---------------------------------------------------------------- USUARIOS
IF OBJECT_ID('dbo.Usuarios', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Usuarios (
        id    INT IDENTITY(1,1) PRIMARY KEY,
        login VARCHAR(50)  NOT NULL UNIQUE,
        senha VARCHAR(255) NOT NULL,          -- guarda o HASH da senha
        tipo  VARCHAR(20)  NOT NULL CONSTRAINT DF_Usuarios_tipo DEFAULT 'cliente'
    );
END;
GO

-- Tabela criada pelo script antigo (sem coluna "tipo")
IF COL_LENGTH('dbo.Usuarios', 'tipo') IS NULL
BEGIN
    ALTER TABLE dbo.Usuarios
        ADD tipo VARCHAR(20) NOT NULL CONSTRAINT DF_Usuarios_tipo DEFAULT 'cliente';
    EXEC('UPDATE dbo.Usuarios SET tipo = login WHERE login IN (''admin'', ''professor'')');
END;
GO

-- Senha antiga era VARCHAR(50); o hash precisa de mais espaco
IF COL_LENGTH('dbo.Usuarios', 'senha') < 255
BEGIN
    ALTER TABLE dbo.Usuarios ALTER COLUMN senha VARCHAR(255) NOT NULL;
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints
               WHERE name = 'CK_Usuarios_tipo' AND parent_object_id = OBJECT_ID('dbo.Usuarios'))
    ALTER TABLE dbo.Usuarios
        ADD CONSTRAINT CK_Usuarios_tipo CHECK (tipo IN ('admin', 'professor', 'cliente'));
GO

-- ---------------------------------------------------------------- PRODUTOS
IF OBJECT_ID('dbo.Produtos', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Produtos (
        id         INT IDENTITY(1,1) PRIMARY KEY,
        nome       VARCHAR(100)   NOT NULL,
        preco      DECIMAL(10, 2) NOT NULL,
        quantidade INT            NOT NULL
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints
               WHERE name = 'CK_Produtos_preco' AND parent_object_id = OBJECT_ID('dbo.Produtos'))
    ALTER TABLE dbo.Produtos ADD CONSTRAINT CK_Produtos_preco CHECK (preco >= 0);
GO

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints
               WHERE name = 'CK_Produtos_quantidade' AND parent_object_id = OBJECT_ID('dbo.Produtos'))
    ALTER TABLE dbo.Produtos ADD CONSTRAINT CK_Produtos_quantidade CHECK (quantidade >= 0);
GO

-- ------------------------------------------------------------------ LIVROS
IF OBJECT_ID('dbo.Livros', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Livros (
        id      INT IDENTITY(1,1) PRIMARY KEY,
        titulo  VARCHAR(150) NOT NULL,
        autor   VARCHAR(100) NOT NULL,
        editora VARCHAR(100) NOT NULL,
        ano     INT          NOT NULL,
        estoque INT          NOT NULL
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints
               WHERE name = 'CK_Livros_ano' AND parent_object_id = OBJECT_ID('dbo.Livros'))
    ALTER TABLE dbo.Livros ADD CONSTRAINT CK_Livros_ano CHECK (ano > 0);
GO

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints
               WHERE name = 'CK_Livros_estoque' AND parent_object_id = OBJECT_ID('dbo.Livros'))
    ALTER TABLE dbo.Livros ADD CONSTRAINT CK_Livros_estoque CHECK (estoque >= 0);
GO

-- ------------------------------------------------------------- EMPRESTIMOS
IF OBJECT_ID('dbo.Emprestimos', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Emprestimos (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        livro_id        INT          NOT NULL,
        nome_aluno      VARCHAR(100) NOT NULL,
        data_emprestimo DATETIME     NOT NULL DEFAULT GETDATE(),
        data_devolucao  DATETIME     NULL,
        CONSTRAINT FK_Emprestimos_Livros FOREIGN KEY (livro_id) REFERENCES dbo.Livros(id)
    );
END;
GO

-- Acelera as consultas de emprestimos em aberto
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'IX_Emprestimos_abertos' AND object_id = OBJECT_ID('dbo.Emprestimos'))
    CREATE INDEX IX_Emprestimos_abertos ON dbo.Emprestimos (livro_id) WHERE data_devolucao IS NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'IX_Emprestimos_livro' AND object_id = OBJECT_ID('dbo.Emprestimos'))
    CREATE INDEX IX_Emprestimos_livro ON dbo.Emprestimos (livro_id);
GO

-- ------------------------------------------------------------ DADOS INICIAIS
IF NOT EXISTS (SELECT 1 FROM dbo.Livros)
BEGIN
    INSERT INTO dbo.Livros (titulo, autor, editora, ano, estoque) VALUES
    ('Grande Sertão: Veredas', 'João Guimarães Rosa', 'Nova Fronteira', 1956, 5),
    ('Vidas Secas', 'Graciliano Ramos', 'Record', 1938, 4),
    ('Capitães da Areia', 'Jorge Amado', 'Companhia das Letras', 1937, 2);
END;
GO

/* RESET (opcional, APAGA TUDO): descomente para recriar do zero e rode o script de novo.
DROP TABLE IF EXISTS dbo.Emprestimos;
DROP TABLE IF EXISTS dbo.Livros;
DROP TABLE IF EXISTS dbo.Produtos;
DROP TABLE IF EXISTS dbo.Usuarios;
GO
*/
