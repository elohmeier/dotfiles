; Generic captures come first; more specific ones below override them.
(ident) @variable

(Param
  (ident) @variable.parameter)

(ObjectField
  key: (ident) @property)

(ExprDotAccess
  (Expr)
  (Expr
    (ExprPath
      (Path
        (ident) @variable.member))))

(Path
  (ident) @module
  "::")

(ExprImport
  "as"
  (ident) @module)

(ExprDeclareVar
  "const"
  name: (ident) @constant)

(ExprFn
  fn_name: (FnDeclName
    (ident) @function))

(ExprCall
  fn_name: (Expr
    (ExprPath
      (Path
        (ident) @function.call .))))

(ExprCall
  fn_name: (Expr
    (ExprDotAccess
      (Expr)
      (Expr
        (ExprPath
          (Path
            (ident) @function.method.call))))))

[
  "const"
  "let"
  "private"
] @keyword

"fn" @keyword.function

[
  "else"
  "if"
  "switch"
] @keyword.conditional

[
  "break"
  "do"
  "for"
  "loop"
  "until"
  "while"
  (ExprContinue)
] @keyword.repeat

"return" @keyword.return

[
  "catch"
  "throw"
  "try"
] @keyword.exception

[
  "as"
  "export"
  "import"
] @keyword.import

"in" @keyword.operator

[
  "!"
  "+"
  "-"
  "="
  "."
  "?."
] @operator

(binop) @operator

((binop) @keyword.operator
  (#eq? @keyword.operator "in"))

(lit_bool) @boolean

(lit_char) @character

(lit_int) @number

(lit_float) @number.float

(lit_str) @string

(str_template_expr
  [
    "${"
    "}"
  ] @punctuation.special)

(SwitchArm
  "_" @character.special)

[
  (comment_line)
  (comment_block)
] @comment @spell

[
  (comment_line_doc)
  (comment_block_doc)
] @comment.documentation @spell

[
  "("
  ")"
  "["
  "]"
  "{"
  "}"
  "#{"
  "?["
  "|"
] @punctuation.bracket

[
  ","
  ":"
  ";"
  "::"
  "=>"
] @punctuation.delimiter
