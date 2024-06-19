"""
A quasi-model object used to represent xml stylesheets (xslt) for package convertion tasks
"""

class XSLT(object):

  # 2017-03-30 TD : snippet used for global xml injection needed as
  #                 iso639 code table for language codes mapping
  #                 (well, only the most likely are included so far...)
  # 2017-05-18 TD : change of tag to <langCodes/> (silly glitch due to
  #                 confusion between xsl:variable langCodes in original 
  #                 langCodeMap.xml file and tag name here...)
  #
  iso639codes = '''
<langCodeMap>
  <langCodes iso639-1="" iso639-2="eng" iso639-3="eng"/>
  <langCodes iso639-1="en" iso639-2="eng" iso639-3="eng"/>
  <langCodes iso639-1="de" iso639-2="deu" iso639-3="deu"/>
  <langCodes iso639-1="nl" iso639-2="nld" iso639-3="nld"/>
  <langCodes iso639-1="fr" iso639-2="fra" iso639-3="fra"/>
  <langCodes iso639-1="es" iso639-2="spa" iso639-3="spa"/>
  <langCodes iso639-1="it" iso639-2="ita" iso639-3="ita"/>
  <langCodes iso639-1="el" iso639-2="ell" iso639-3="ell"/>
  <langCodes iso639-1="fi" iso639-2="fin" iso639-3="fin"/>
  <langCodes iso639-1="ru" iso639-2="rus" iso639-3="rus"/>
  <langCodes iso639-1="he" iso639-2="heb" iso639-3="heb"/>
</langCodeMap>
  '''

  # 2017-07-12 TD : snippet needed for conversion of name of months to numbers
  #                 (hip, hip, hooray, thanks to RSC...)
  #
  mnth2number = '''
<monthNameMap>
  <monthNames text="" number="12"/>
  <monthNames text="January" number="01"/>
  <monthNames text="Jan" number="01"/>
  <monthNames text="jan" number="01"/>
  <monthNames text="February" number="02"/>
  <monthNames text="Feb" number="02"/>
  <monthNames text="feb" number="02"/>
  <monthNames text="March" number="03"/>
  <monthNames text="Mar" number="03"/>
  <monthNames text="mar" number="03"/>
  <monthNames text="April" number="04"/>
  <monthNames text="Apr" number="04"/>
  <monthNames text="apr" number="04"/>
  <monthNames text="May" number="05"/>
  <monthNames text="may" number="05"/>
  <monthNames text="June" number="06"/>
  <monthNames text="Jun" number="06"/>
  <monthNames text="jun" number="06"/>
  <monthNames text="July" number="07"/>
  <monthNames text="Jul" number="07"/>
  <monthNames text="jul" number="07"/>
  <monthNames text="August" number="08"/>
  <monthNames text="Aug" number="08"/>
  <monthNames text="aug" number="08"/>
  <monthNames text="September" number="09"/>
  <monthNames text="Sep" number="09"/>
  <monthNames text="sep" number="09"/>
  <monthNames text="October" number="10"/>
  <monthNames text="Oct" number="10"/>
  <monthNames text="oct" number="10"/>
  <monthNames text="November" number="11"/>
  <monthNames text="Nov" number="11"/>
  <monthNames text="nov" number="11"/>
  <monthNames text="December" number="12"/>
  <monthNames text="Dec" number="12"/>
  <monthNames text="dec" number="12"/>
  <monthNames text="Unassigned" number="12"/>
  <monthNames text="unassigned" number="12"/>
</monthNameMap>
  '''

    # 2017-03-22 TD : static(!!) strings containing the xsl code JATS --> OPUS4
  #                 Note that there MUST NOT be any kind of '<?xml ...?>' header!
  #
  # 2019-08-13 TD : Change of the output "issn" in the tag "identifiers": no distinction
  #                 between eISSN and pISSN anymore! In fact, OPUS4 article data model
  #                 does not support these subtypes as identifier.
  #
  # 2019-08-28 TD : Keywords are checked for string-length() > 0: 'empty' keywords are skipped!
  #
  # 2019-09-24 TD : Eliminate the tag 'journal-title-group' in xpath since a publisher
  #                 (i.e. Frontiers) apparently is not using it
  #
  jats2opus4 = '''
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

  <!-- <xsl:import href="outputTokens.xsl"/> -->
  <xsl:output method="xml" omit-xml-declaration="yes" indent="yes" encoding="utf-8"/>

  <xsl:variable name="inject1">
    {xmlinject1}
  </xsl:variable>
   <xsl:variable name="inject2">
    {xmlinject2}
  </xsl:variable>
  <xsl:variable name="langIn" select="translate(/article/@xml:lang,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"/>
  <!-- <xsl:variable name="langOut">eng</xsl:variable> -->
  <xsl:variable name="langOut" select="document('')//langCodeMap/langCodes[@iso639-1=$langIn]/@iso639-2"/>

  <xsl:template match="/">
  <import>
    <opusDocument>
          <xsl:attribute name="language">
            <xsl:value-of select="$langOut"/>
          </xsl:attribute>
          <xsl:attribute name="type">
            <xsl:text>article</xsl:text>
          </xsl:attribute>
          <xsl:if test="//article-meta/fpage">
            <xsl:attribute name="pageFirst">
              <xsl:value-of select="//article-meta/fpage"/>
            </xsl:attribute>
          </xsl:if>
          <xsl:if test="//article-meta/lpage">
            <xsl:attribute name="pageLast">
              <xsl:value-of select="//article-meta/lpage"/>
            </xsl:attribute>
          </xsl:if>
          <xsl:if test="//article-meta/volume">
            <xsl:attribute name="volume">
              <xsl:value-of select="//article-meta/volume"/>
            </xsl:attribute>
          </xsl:if>
          <xsl:if test="//article-meta/issue">
            <xsl:attribute name="issue">
              <xsl:value-of select="//article-meta/issue"/>
            </xsl:attribute>
          </xsl:if>
          <xsl:attribute name="publisherName">
            <xsl:value-of select="//journal-meta/publisher/publisher-name"/>
          </xsl:attribute>
          <xsl:if test="//journal-meta/publisher/publisher-loc">
            <xsl:attribute name="publisherPlace">
              <xsl:value-of select="//journal-meta/publisher/publisher-loc"/>
            </xsl:attribute>
          </xsl:if>
          <xsl:attribute name="belongsToBibliography">
            <xsl:text>false</xsl:text>
          </xsl:attribute>
          <xsl:attribute name="serverState">
            <xsl:text>unpublished</xsl:text>
          </xsl:attribute>
          <xsl:if test="//article-meta/counts/page-count/@count">
            <xsl:attribute name="pageNumber">
              <xsl:value-of select="//article-meta/counts/page-count/@count"/>
            </xsl:attribute>
          </xsl:if>
          <!--
          language="eng"
          type="article|bachelorthesis|bookpart|book|conferenceobject|contributiontoperiodical|coursematerial|diplom|doctoralthesis|examen|habilitation|image|lecture|magister|masterthesis|movingimage|other|periodical|preprint|report|review|studythesis|workingpaper"
          pageFirst=""
          pageLast=""
          edition=""
          volume=""
          issue=""
          publisherName=""
          publisherPlace=""
          creatingCorporation=""
          contributingCorporation=""
          belongsToBibliography="true|false"
          serverState="audited|published|restricted|inprogress|unpublished"
          -->

      <!-- Title Information -->
      <titlesMain>
          <titleMain>
            <xsl:attribute name="language"><xsl:value-of select="$langOut"/></xsl:attribute>
            <xsl:value-of select="normalize-space(//article-meta/title-group/article-title)"/>
          </titleMain>
          <xsl:for-each select="//article-meta/title-group/trans-title-group/trans-title">
            <titleMain>
              <xsl:call-template name="insert-lang-attribute"/>
              <xsl:value-of select="normalize-space()"/>
            </titleMain>
          </xsl:for-each>
      </titlesMain>
      <titles>
          <xsl:for-each select="//journal-meta//journal-title">
            <title>
              <xsl:attribute name="language"><xsl:value-of select="$langOut"/></xsl:attribute>
              <xsl:attribute name="type"><xsl:text>parent</xsl:text></xsl:attribute>
              <xsl:value-of select="normalize-space()"/>
            </title>
          </xsl:for-each>
          <xsl:if test="//article-meta/title-group/subtitle">
            <title>
              <xsl:attribute name="language"><xsl:value-of select="$langOut"/></xsl:attribute>
              <xsl:attribute name="type"><xsl:text>sub</xsl:text></xsl:attribute>
              <xsl:value-of select="normalize-space(//article-meta/title-group/subtitle)"/>
            </title>
          </xsl:if>
          <xsl:for-each select="//article-meta/title-group/trans-title-group/trans-subtitle">
            <title>
              <xsl:call-template name="insert-lang-attribute"/>
              <xsl:attribute name="type"><xsl:text>sub</xsl:text></xsl:attribute>
              <xsl:value-of select="normalize-space()"/>
            </title>
          </xsl:for-each>
      </titles>

      <!-- Abstract(s) -->
      <xsl:if test="//article-meta/abstract or //article-meta/trans-abstract">
      <abstracts>
          <xsl:for-each select="//article-meta/abstract[1]">
          <!-- selecting only the first abstract since opus only accepts one abstract per language! -->
            <abstract>
              <xsl:attribute name="language"><xsl:value-of select="$langOut"/></xsl:attribute>
              <xsl:call-template name="abstract-nested-whitespacing"/>
            </abstract>
          </xsl:for-each>
          <xsl:for-each select="//article-meta/trans-abstract">
            <abstract>
              <xsl:call-template name="insert-lang-attribute"/>
              <xsl:call-template name="abstract-nested-whitespacing"/>
            </abstract>
          </xsl:for-each>
      </abstracts>
      </xsl:if>

      <!-- Author Information, only editors and authors due to value constraints in OPUS-xml-->
      <persons>
          <xsl:for-each select="//article-meta/contrib-group/contrib">
            <xsl:if test="@contrib-type='guest-editor' or
                          @contrib-type='editor' or
                          @contrib-type='author'">
              <person>
                <xsl:attribute name="role">
                  <xsl:choose>
                      <xsl:when test="@contrib-type='author'">
                      <xsl:value-of select="@contrib-type"/>
                    </xsl:when>
                    <xsl:when test="@contrib-type='guest-editor' or
                                    @contrib-type='editor'">
                      <xsl:text>editor</xsl:text>
                    </xsl:when>
                  </xsl:choose>
                </xsl:attribute>

                <xsl:choose>
                    <xsl:when test="collab">
                      <xsl:attribute name="firstName">-</xsl:attribute>
                      <xsl:choose>
                        <xsl:when test="collab/institution">
                        <xsl:attribute name="lastName"><xsl:value-of select="collab/institution/text()"/></xsl:attribute>
                        </xsl:when>
                        <xsl:otherwise>
                        <xsl:attribute name="lastName"><xsl:value-of select="collab/text()"/></xsl:attribute>
                        </xsl:otherwise>
                      </xsl:choose>
                    </xsl:when>
                    <xsl:otherwise>
                        <xsl:attribute name="firstName"><xsl:value-of select=".//given-names"/></xsl:attribute>
                        <xsl:attribute name="lastName"><xsl:value-of select=".//surname"/></xsl:attribute>
                    </xsl:otherwise>
                </xsl:choose>

                <xsl:if test=".//email">
                  <xsl:attribute name="email"><xsl:value-of select=".//email"/></xsl:attribute>
                </xsl:if>

                <xsl:if test="contains(contrib-id/@contrib-id-type,'orcid')">
                <identifiers>
                  <identifier>
                    <xsl:attribute name="type"><xsl:text>orcid</xsl:text></xsl:attribute>
                    <xsl:variable name='orcid' select="contrib-id[@contrib-id-type='orcid']/text()"/>

                    <xsl:choose>
                    <xsl:when test="substring($orcid, string-length($orcid))='/'">
                      <xsl:variable name="orcid2" select="substring($orcid, 1, string-length($orcid)-1)"/>
                      <xsl:call-template name="cut-orcid">
                        <xsl:with-param name="orcid" select="$orcid2"/>
                      </xsl:call-template>
                    </xsl:when>
                    <xsl:otherwise>
                      <xsl:call-template name="cut-orcid">
                        <xsl:with-param name="orcid" select="$orcid"/>
                      </xsl:call-template>
                    </xsl:otherwise>
                    </xsl:choose>
                  </identifier>
                </identifiers>
                </xsl:if>
              </person>
            </xsl:if>
          </xsl:for-each>
      </persons>

      <!-- Topical Keywords -->
      <keywords>
          <keyword>
            <xsl:attribute name="language"><xsl:value-of select="$langOut"/></xsl:attribute>
            <xsl:attribute name="type"><xsl:text>swd</xsl:text></xsl:attribute>
            <xsl:text>-</xsl:text>
          </keyword>
          <xsl:for-each select="//article-meta/kwd-group/kwd">
            <xsl:if test="string-length(normalize-space(text()))>0">
              <keyword>
                <xsl:call-template name="insert-lang-attribute"/>
                <xsl:attribute name="type"><xsl:text>uncontrolled</xsl:text></xsl:attribute>
                <xsl:value-of select="normalize-space(text())"/>
              </keyword>
            </xsl:if>
          </xsl:for-each>
      </keywords>

      <!--
      <dnbInstitutions>
          <dnbInstitution id="<integer>" role="grantor|publisher"/>
      </dnbInstitutions>
      -->

      <!-- Publication Dates -->
      <dates>
        <xsl:for-each select="//article-meta/pub-date">
        <xsl:choose>
          <xsl:when test="(contains(@pub-type,'epub') and year) or
              (contains(@pub-type,'ppub') and year) or
              (contains(@pub-type, 'epub-ppub') and year) or
              (contains(@date-type,'pub') and year) or
              not(@*)">
              <xsl:call-template name="compose-date"> </xsl:call-template>
          </xsl:when>
          <xsl:otherwise>
            <xsl:if test="not(year)">
            <!--to comply with opus requirement that a date has to be given-->
            <date>
              <xsl:attribute name="type"><xsl:text>completed</xsl:text></xsl:attribute>
              <xsl:attribute name="monthDay">
                <xsl:text>--11-11</xsl:text>
              </xsl:attribute>
              <xsl:attribute name="year">
                <xsl:text>1111</xsl:text>
              </xsl:attribute>
            </date>
            </xsl:if>
          </xsl:otherwise>
        </xsl:choose>
        </xsl:for-each>
      </dates>

      <!-- Identifiers, ISSN, DOI, PMID -->
      <identifiers>
        <xsl:for-each select="//journal-meta/issn">
          <identifier>
            <xsl:attribute name="type"><xsl:text>issn</xsl:text></xsl:attribute>
            <xsl:value-of select="normalize-space(text())"/>
          </identifier>
        </xsl:for-each>
        <xsl:if test="//article-meta/article-id[@pub-id-type='doi']">
          <identifier>
             <xsl:attribute name="type"><xsl:text>doi</xsl:text></xsl:attribute>
             <xsl:value-of select="//article-meta/article-id[@pub-id-type='doi']"/>
          </identifier>
        </xsl:if>
        <xsl:if test="//article-meta/article-id[@pub-id-type='pmid']">
          <identifier>
             <xsl:attribute name="type"><xsl:text>pmid</xsl:text></xsl:attribute>
             <xsl:value-of select="//article-meta/article-id[@pub-id-type='pmid']"/>
          </identifier>
        </xsl:if>
      </identifiers>


      <!--
      <identifiers>
          <identifier>
             <xsl:attribute name="type"><xsl:text>issn</xsl:text></xsl:attribute>
             <xsl:for-each select="//journal-meta/issn[@pub-type='ppub' or @publication-format='print']">
                <xsl:value-of select="normalize-space(text())"/>
                <xsl:if test="position() != last()">
                   <xsl:text> , </xsl:text>
                </xsl:if>
                <xsl:if test="position() = last()">
                   <xsl:text> (pISSN)</xsl:text>
                </xsl:if>
             </xsl:for-each>
             <xsl:if test="//journal-meta/issn[@pub-type='epub' or @publication-format='electronic']">
                <xsl:text> ; </xsl:text>
                <xsl:for-each select="//journal-meta/issn[@pub-type='epub' or @publication-format='electronic']">
                   <xsl:value-of select="normalize-space(text())"/>
                   <xsl:if test="position() != last()">
                      <xsl:text> , </xsl:text>
                   </xsl:if>
                   <xsl:if test="position() = last()">
                      <xsl:text> (eISSN)</xsl:text>
                   </xsl:if>
                </xsl:for-each>
             </xsl:if>
          </identifier>
          <identifier>
             <xsl:attribute name="type"><xsl:text>doi</xsl:text></xsl:attribute>
             <xsl:value-of select="//article-meta/article-id[@pub-id-type='doi']"/>
          </identifier>
        <xsl:if test="//article-meta/article-id[@pub-id-type='pmid']">
          <identifier>
             <xsl:attribute name="type"><xsl:text>pmid</xsl:text></xsl:attribute>
             <xsl:value-of select="//article-meta/article-id[@pub-id-type='pmid']"/>
          </identifier>
        </xsl:if>
      </identifiers>
      -->

      <!--
      <notes>
          <note visibility="private|public">?????</note>
      </notes>
      <collections>
          <collection id="<integer>"/>
      </collections>
      <series>
          <seriesItem id="<integer>" number=""/>
      </series>
      <enrichments>
          <enrichment key="">?????</enrichment>
      </enrichments>
      <licences>
          <licence id="<integer>"/>
      </licences>
      <files basedir="">
          <file
                path=""
                name=""
                language=""
                displayName=""
                visibleInOai="true|false"
                visibleInFrontdoor="true|false"
                sortOrder="<int>">
            <comment>?????</comment>
            <checksum type="md5|sha256|sha512">?????</checksum>
          </file>
      </files>
      -->
    </opusDocument>
  </import>
  </xsl:template>

  <xsl:template name="compose-date">
    <xsl:param name="xpath" select="."/>
          <date>
             <xsl:attribute name="type"><xsl:text>published</xsl:text></xsl:attribute>
             <xsl:if test="$xpath/month">
                <xsl:variable name="mnth" select="$xpath/month"/>
                <xsl:attribute name="monthDay">
                  <xsl:text>--</xsl:text>
                   <xsl:choose>
                        <xsl:when test="number($mnth) = $mnth">
                            <xsl:value-of select="format-number($mnth,'00')"/>
                        </xsl:when>
                        <xsl:when test="document('')//monthNameMap/monthNames[@text=$mnth]/@number">
                            <xsl:value-of select="document('')//monthNameMap/monthNames[@text=$mnth]/@number"/>
                        </xsl:when>
                        <xsl:otherwise>
                            <xsl:text>01</xsl:text>
                        </xsl:otherwise>
                    </xsl:choose>
                  <xsl:text>-</xsl:text>
                  <xsl:choose>
                    <xsl:when test="$xpath/day">
                      <xsl:value-of select="format-number($xpath/day,'00')"/>
                    </xsl:when>
                    <xsl:otherwise>
                      <xsl:text>01</xsl:text>
                    </xsl:otherwise>
                  </xsl:choose>
                </xsl:attribute>
             </xsl:if>
             <xsl:attribute name="year">
                <xsl:value-of select="$xpath/year"/>
             </xsl:attribute>
          </date>
  </xsl:template>

  <xsl:template name="insert-lang-attribute">
    <xsl:choose>
        <xsl:when test="@xml:lang">
            <xsl:variable name="lang2" select="translate(@xml:lang,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"/>
            <xsl:variable name="lang3" select="document('')//langCodeMap/langCodes[@iso639-1=$lang2]/@iso639-2"/>
            <xsl:attribute name="language"><xsl:value-of select="$lang3"/></xsl:attribute>
        </xsl:when>
        <xsl:when test="../@xml:lang">
            <xsl:variable name="lang2" select="translate(../@xml:lang,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"/>
            <xsl:variable name="lang3" select="document('')//langCodeMap/langCodes[@iso639-1=$lang2]/@iso639-2"/>
            <xsl:attribute name="language"><xsl:value-of select="$lang3"/></xsl:attribute>
        </xsl:when>
        <xsl:otherwise>
          <xsl:attribute name="language"><xsl:value-of select="$langOut"/></xsl:attribute>
        </xsl:otherwise>
        </xsl:choose>
  </xsl:template>

  <xsl:template name="cut-orcid">
    <xsl:param name="orcid"/>
    <!-- This template accepts an url as input and selects the substring after the last "/".
    orcids consist of four 4-digit blocks, separated by dashes. i.e. the resulting string should be precisely 19 characters long.
    Lacking any regex capabilities in xslt 1.0, the template makes a last check for string-length before returning the orcid-id.
    Recursive template, as substring-after() can only ever select the substring after the first instance of a character.
    -->
    <xsl:choose>
      <xsl:when test="not(contains($orcid,'/'))">
        <xsl:if test="string-length($orcid)=19">
          <xsl:value-of select="$orcid"/>
        </xsl:if>
      </xsl:when>
      <xsl:otherwise>
        <xsl:call-template name="cut-orcid">
        <xsl:with-param name="orcid" select="substring-after($orcid,'/')"/>
        </xsl:call-template>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <xsl:template name="abstract-nested-whitespacing">
    <!-- this template transforms abstract content to normalize whitespacing between child elements.
    if abstract contains sub elements, it likely contains chemical formulas and the text contents will be used as is.
    Otherwise, this template deliberately adds white spaces between the text contents of each child element. If the current element is a title element, line breaks will be added before and after the current text to improve readability and approximate intended document structure. -->
    <xsl:choose>
      <xsl:when test="descendant::sub">
        <xsl:for-each select="descendant-or-self::text()">
          <xsl:if test="string-length(normalize-space())&gt;0">
            <xsl:choose>
              <xsl:when test="local-name(parent::*) = 'tex-math'">
              <!--ignore tex-math elements-->
              </xsl:when>
              <xsl:otherwise>
                <xsl:value-of select="."/>
              </xsl:otherwise>
            </xsl:choose>
          </xsl:if>
        </xsl:for-each>
      </xsl:when>
      <xsl:otherwise>
        <xsl:for-each select="descendant-or-self::text()">
          <xsl:if test="string-length(normalize-space())&gt;0">
            <xsl:choose>
              <xsl:when test="local-name(parent::*)='title' "> <!-- when text of title element is selected, add line breaks before and after-->
                <xsl:text>
                </xsl:text>
                <xsl:value-of select="normalize-space()"/>
                <xsl:text>
                </xsl:text>
              </xsl:when>
              <xsl:when test="local-name(parent::*) = 'tex-math'">
              <!--ignore tex-math elements-->
              </xsl:when>
              <xsl:when test="contains(name(parent::*),'mml:')">
                <xsl:value-of select="."/>
              </xsl:when>
              <xsl:otherwise> <!--otherwise select space-normalized text and add a whitespace afterward-->
                <xsl:value-of select="normalize-space()"/>
                <xsl:text> </xsl:text>
              </xsl:otherwise>
            </xsl:choose>
          </xsl:if>
        </xsl:for-each>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>


</xsl:stylesheet>
'''.format(xmlinject1=iso639codes,xmlinject2=mnth2number)




  # 2017-07-11 TD : static string containing the xsl code for JATS --> METSMODS
  #                 Note that there MUST NOT be any kind of '<?xml ...?>' header!
  #
  # 2019-09-24 TD : Eliminate the tag 'journal-title-group' in xpath since a publisher
  #                 (i.e. Frontiers) apparently is not using it
  #
  jats2metsmods = '''
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

    <!-- <xsl:import href="jats2mods.xsl"/> -->
    <xsl:output method="xml" omit-xml-declaration="no" standalone="no" indent="yes" encoding="utf-8"/>

    <xsl:param name="currdatetime">1970-01-01T00:00:00</xsl:param>

    <xsl:variable name="inject">
      {xmlinject}
    </xsl:variable>

    <xsl:template match="/">
        <mets:mets xmlns:mets="http://www.loc.gov/METS/"
                   xmlns:mods="http://www.loc.gov/mods/v3"
              xmlns:xlink="http://www.w3.org/1999/xlink"
              xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
              xsi:schemaLocation="http://www.loc.gov/METS/ http://www.loc.gov/mets/mets.xsd http://www.loc.gov/mods/v3 https://www.loc.gov/standards/mods/v3/mods.xsd">
            <xsl:attribute name="ID"><xsl:text>sword-mets_mets</xsl:text></xsl:attribute>
            <xsl:attribute name="OBJID"><xsl:text>sword-mets</xsl:text></xsl:attribute>
            <xsl:attribute name="LABEL"><xsl:text>METS/MODS SWORD Item</xsl:text></xsl:attribute>
            <xsl:attribute name="PROFILE"><xsl:text>METS/MODS SIP Profile 1.0</xsl:text></xsl:attribute>
            <mets:metsHdr>
                <xsl:attribute name="CREATEDATE"><xsl:value-of select="$currdatetime"/></xsl:attribute>
                <mets:agent>
                    <xsl:attribute name="ROLE">CUSTODIAN</xsl:attribute>
                    <xsl:attribute name="TYPE">ORGANIZATION</xsl:attribute>
                    <mets:name>DeepGreen</mets:name>
                </mets:agent>
            </mets:metsHdr>
            <mets:dmdSec>
                <xsl:attribute name="ID">sword-mets-dmd-1</xsl:attribute>
                <xsl:attribute name="GROUPID">sword-mets-dmd-1_group-1</xsl:attribute>
                <mets:mdWrap>
                    <xsl:attribute name="LABEL"><xsl:text>SWAP Metadata</xsl:text></xsl:attribute>
                    <xsl:attribute name="MDTYPE">MODS</xsl:attribute>
                    <xsl:attribute name="MIMETYPE"><xsl:text>text/xml</xsl:text></xsl:attribute>
                    <mets:xmlData>
                        <xsl:apply-templates/>
                    </mets:xmlData>
                </mets:mdWrap>
            </mets:dmdSec>
        </mets:mets>
    </xsl:template>


    <!--
    <xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
        <xsl:output method="xml" omit-xml-declaration="no" standalone="no" indent="yes" encoding="utf-8"/>
    -->

    <!-- (Possible) mapping of affiliation(s) -->
    <xsl:key name="kAffById" match="//aff" use="@id"/>

    <xsl:template match="/article">
        <mods:mods xmlns:mods="http://www.loc.gov/mods/v3"
                   xmlns:xlink="http://www.w3.org/1999/xlink"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                   xsi:schemaLocation="http://www.loc.gov/mods/v3 https://www.loc.gov/standards/mods/v3/mods-3-6.xsd">

            <!--
                Since we are mapping JATS, we are only dealing with journal articles.
                According to a LOC example, these are attributed as follows.
                See https://www.loc.gov/standards/mods/v3/mods-userguide-examples.html#journal_article
            -->
            <mods:typeOfResource>text</mods:typeOfResource>
            <mods:genre>journal article</mods:genre>

            <!-- Language -->
            <mods:language>
                <mods:languageTerm type="code" authority="rfc3066">
                    <xsl:choose>
                        <xsl:when test="//article/@xml:lang">
                            <xsl:value-of select="//article/@xml:lang"/>
                        </xsl:when>
                        <xsl:otherwise>
                            <xsl:text>en</xsl:text>
                        </xsl:otherwise>
                    </xsl:choose>
                </mods:languageTerm>
            </mods:language>

            <!-- Title -->
            <mods:titleInfo>
                <xsl:for-each select="//article-meta/title-group/article-title">
                    <mods:title>
                        <xsl:call-template name="insert-lang-attribute"/>
                        <xsl:value-of select="normalize-space()"/>
                    </mods:title>
                </xsl:for-each>
                <xsl:for-each select="//article-meta/title-group/subtitle">
                    <mods:subTitle>
                        <xsl:call-template name="insert-lang-attribute"/>
                        <xsl:value-of select="normalize-space()"/>
                    </mods:subTitle>
                </xsl:for-each>
            </mods:titleInfo>
            <xsl:for-each select="//article-meta/title-group/trans-title-group/trans-title">
                <mods:titleInfo type="translated">
                    <mods:title>
                        <xsl:call-template name="insert-lang-attribute"/>
                        <xsl:value-of select="normalize-space()"/>
                    </mods:title>
                </mods:titleInfo>
            </xsl:for-each>
            <xsl:for-each select="//article-meta/title-group/trans-title-group/trans-subtitle">
                <mods:titleInfo type="translated">
                    <mods:subTitle>
                        <xsl:call-template name="insert-lang-attribute"/>
                        <xsl:value-of select="normalize-space()"/>
                    </mods:subTitle>
                </mods:titleInfo>
            </xsl:for-each>

            <!-- Appearance (journal title, issn, volume, issue, pages) -->
            <mods:relatedItem type="host">
                <mods:titleInfo>
                    <xsl:for-each select="//journal-meta//journal-title">
                        <mods:title>
                            <xsl:call-template name="insert-lang-attribute"/>
                            <xsl:value-of select="normalize-space()"/>
                        </mods:title>
                    </xsl:for-each>
                </mods:titleInfo>
                  
                <xsl:for-each select="//journal-meta//abbrev-journal-title">
                  <mods:titleInfo> 
                    <xsl:attribute name="type">abbreviated</xsl:attribute>
                    <mods:title>
                      <xsl:call-template name="insert-lang-attribute"/>
                      <xsl:value-of select="normalize-space()"/>
                    </mods:title>
                  </mods:titleInfo>
                </xsl:for-each>

                <xsl:for-each select="//journal-meta/issn">
                    <xsl:choose>
                        <xsl:when test="@pub-type='epub' or @publication-format='electronic' or @publication-format='epub'">
                            <mods:identifier type="eIssn"><xsl:value-of select="."/></mods:identifier>
                        </xsl:when>
                        <xsl:otherwise>
                        <mods:identifier type="issn">
                            <xsl:value-of select="."/>
                        </mods:identifier>
                        </xsl:otherwise>
                    </xsl:choose>
                </xsl:for-each>

                <xsl:for-each select="//journal-meta/journal-id">
                    <mods:identifier>
                        <xsl:attribute name="type"><xsl:value-of select="@journal-id-type"/></xsl:attribute>
                        <xsl:value-of select="."/>
                    </mods:identifier>
                </xsl:for-each>
                
                <mods:part>
                    <xsl:if test="//article-meta/volume">
                        <mods:detail type="volume">
                            <mods:number><xsl:value-of select="//article-meta/volume"/></mods:number>
                        </mods:detail>
                    </xsl:if>
                    <xsl:if test="//article-meta/issue">
                        <mods:detail type="issue">
                            <mods:number><xsl:value-of select="//article-meta/issue"/></mods:number>
                        </mods:detail>
                    </xsl:if>
                    <xsl:if test="//article-meta/fpage or //article-meta/counts/page-count/@count">
                        <mods:extent unit="pages">
                            <xsl:if test="//article-meta/fpage">
                                <mods:start><xsl:value-of select="//article-meta/fpage"/></mods:start>
                            </xsl:if>
                            <xsl:if test="//article-meta/lpage">
                                <mods:end><xsl:value-of select="//article-meta/lpage"/></mods:end>
                            </xsl:if>
                            <xsl:if test="//article-meta/counts/page-count/@count">
                                <mods:total><xsl:value-of select="//article-meta/counts/page-count/@count"/></mods:total>
                            </xsl:if>
                        </mods:extent>
                    </xsl:if>
                </mods:part>
            </mods:relatedItem>

            <!-- Creator / Contributor (Author, Editor...)-->
            <xsl:for-each select="//article-meta/contrib-group/contrib">
              <xsl:choose>
                    <!-- if contributor is a non-person entity -->
                    <xsl:when test="collab">
                        <mods:name type="corporate">
                        <mods:namePart>
                        <xsl:choose>
                            <xsl:when test="collab/institution">
                                <xsl:value-of select="collab/institution/text()"/>
                            </xsl:when>
                            <xsl:otherwise>
                                <xsl:value-of select="collab/text()"/>
                            </xsl:otherwise>
                        </xsl:choose>
                        </mods:namePart>
                        <mods:role>
                            <mods:roleTerm type="text"><xsl:value-of select="@contrib-type"/></mods:roleTerm>
                        </mods:role>
                        </mods:name>

                    </xsl:when>


                  <!-- if contributor is a person -->
                  <xsl:when test="//string-name or //name">
                      <mods:name type="personal">
                          <mods:namePart type="family"><xsl:value-of select=".//surname"/></mods:namePart>
                          <xsl:if test="string-length(.//given-names/text()) > 0">
                            <mods:namePart type="given"><xsl:value-of select=".//given-names"/></mods:namePart>
                          </xsl:if>
                          <mods:role>
                              <mods:roleTerm type="text"><xsl:value-of select="@contrib-type"/></mods:roleTerm>
                          </mods:role>
                          <!-- Identifier: So far, support of ORCIDs (and email adresses?) only -->
                          <xsl:if test="contains(contrib-id/@contrib-id-type,'orcid')">
                              <mods:nameIdentifier type="orcid">
                                  <xsl:copy-of select="contrib-id[@contrib-id-type='orcid']/text()"/>
                              </mods:nameIdentifier>
                          </xsl:if>
                          <xsl:if test="string-length(.//email/text()) > 0">
                            <mods:nameIdentifier type="email">
                              <xsl:value-of select=".//email"/>
                            </mods:nameIdentifier>
                          </xsl:if>

                          <!-- Affiliations -->
                          <xsl:for-each select="xref[@ref-type='aff']">
                            <xsl:choose>
                              <xsl:when test="contains(./@ref-type,'aff') and string-length(@rid) > 0">
                                <mods:affiliation>

                                  <xsl:call-template name="build_aff_string">
                                    <xsl:with-param name="aff_node" select="key('kAffById',@rid)"/>
                                    <xsl:with-param name="combined_string" select="''"/>
                                    <xsl:with-param name="current_position" select="1"/>
                                  </xsl:call-template>
                                </mods:affiliation>
                              </xsl:when>
                              <xsl:when test="string-length(//aff[position()=last()]/text()) > 0">
                                  <mods:affiliation>
                                    <xsl:call-template name="build_aff_string">
                                      <xsl:with-param name="aff_node" select="//aff[position()=last()]"/>
                                      <xsl:with-param name="combined_string" select="''"/>
                                      <xsl:with-param name="current_position" select="1"/>
                                    </xsl:call-template>
                                  </mods:affiliation>
                              </xsl:when>
                            </xsl:choose>
                          </xsl:for-each>

                          <!-- accommodate aff linking via @rid in contrib element, multiple ids separated by spaces -->
                          <xsl:if test="not(xref[@ref-type='aff']) and @rid">
                              <xsl:call-template name="parse-multiple-rids-for-affs">
                                  <xsl:with-param name="rid_string" select="@rid"/>
                              </xsl:call-template>
                          </xsl:if>

                          <!-- if the current contrib element contains the affiliation itself, without any rids: -->
                          <xsl:if test=".//aff">
                              <mods:affiliation>
                                  <xsl:value-of select="normalize-space(.//aff)"/>
                              </mods:affiliation>
                          </xsl:if>
                      </mods:name>
                    </xsl:when>

                </xsl:choose>

            </xsl:for-each>

            <!-- Description: Abstract / TOC -->
            <xsl:for-each select="//article-meta/abstract">
                <xsl:choose>
                    <xsl:when test="@type = 'toc'">
                        <mods:tableOfContents>
                            <xsl:call-template name="insert-lang-attribute"/>
                            <xsl:value-of select="."/>
                        </mods:tableOfContents>
                    </xsl:when>
                    <xsl:otherwise>
                        <mods:abstract>
                            <xsl:call-template name="insert-lang-attribute"/>
                            <xsl:call-template name="abstract-nested-whitespacing"/>
                        </mods:abstract>
                    </xsl:otherwise>
                </xsl:choose>
            </xsl:for-each>
            <xsl:for-each select="//article-meta/trans-abstract">
              <mods:abstract>
                <xsl:call-template name="insert-lang-attribute"/>
                <xsl:call-template name="abstract-nested-whitespacing" />
              </mods:abstract>
            </xsl:for-each>

            <!-- Description: Subject (Keywords) -->
            <xsl:if test="//article-meta/kwd-group/kwd">
                <mods:subject>
                    <xsl:for-each select="//article-meta/kwd-group/kwd">
                        <mods:topic>
                          <xsl:call-template name="insert-lang-attribute"/>
                          <xsl:value-of select="."/>
                        </mods:topic>
                    </xsl:for-each>
                </mods:subject>
            </xsl:if>

            <!-- Publisher, Dates (in MODS under originInfo) -->
            <mods:originInfo>
                <xsl:if test="//journal-meta/publisher/publisher-name">
                    <mods:publisher><xsl:value-of select="//journal-meta/publisher/publisher-name"/></mods:publisher>
                </xsl:if>
                <xsl:if test="//journal-meta/publisher/publisher-loc">
                    <mods:place>
                        <mods:placeTerm type="text"><xsl:value-of select="//journal-meta/publisher/publisher-loc"/></mods:placeTerm>
                    </mods:place>
                </xsl:if>


                <!-- Publication date (= date available/issued) -->
                <xsl:for-each select="//article-meta/pub-date">
                    <xsl:if test="(contains(@pub-type, 'epub') and year and month) or
                        (contains(@pub-type, 'epub-ppub') and year and month) or
                        (contains(@pub-type, 'ppub') and year and month) or
                        (contains(@date-type, 'pub') and year and month)
                        or not(@*)">
                            <mods:dateIssued encoding="w3cdtf">
                            <xsl:call-template name="compose-date"></xsl:call-template>
                        </mods:dateIssued>
                    </xsl:if>
                </xsl:for-each>

                <!-- Other dates (received, accepted...) -->
                <xsl:for-each select="//article-meta/history/date">
                    <xsl:if test="year and month">
                        <mods:dateOther encoding="w3cdtf">
                            <xsl:attribute name="type"><xsl:value-of select="@date-type"/></xsl:attribute>
                            <xsl:call-template name="compose-date"></xsl:call-template>
                        </mods:dateOther>
                    </xsl:if>
                </xsl:for-each>

                <!-- another uncommon variation of the same:-->
                <xsl:for-each select="//article-meta/pub-history/event/date">
                    <xsl:if test="year and month">
                            <xsl:if test="@date-type">
                                <mods:dateOther encoding="w3cdtf">
                                <xsl:attribute name="type"><xsl:value-of select="@date-type"/></xsl:attribute>
                                <xsl:call-template name="compose-date"></xsl:call-template>
                                </mods:dateOther>
                            </xsl:if>
                            <xsl:if test="../@event-type">
                                <mods:dateOther encoding="w3cdtf">
                                <xsl:attribute name="type"><xsl:value-of select="../@event-type"/></xsl:attribute>
                                <xsl:call-template name="compose-date"></xsl:call-template>
                            </mods:dateOther>
                            </xsl:if>
                    </xsl:if>
                </xsl:for-each>
            </mods:originInfo>

            <!-- Identifiers -->
            <xsl:for-each select="//article-meta/article-id">
                <mods:identifier>
                    <xsl:attribute name="type"><xsl:value-of select="@pub-id-type"/></xsl:attribute>
                    <xsl:value-of select="."/>
                </mods:identifier>
            </xsl:for-each>

            <!-- License / Copyright -->
            <xsl:for-each select="//article-meta/permissions/license">
                <mods:accessCondition type="use and reproduction">
                    <xsl:choose>
                        <xsl:when test=".//@xlink:href">
                            <xsl:attribute name="xlink:href"><xsl:value-of select=".//@xlink:href"/></xsl:attribute>
                        </xsl:when>
                        <xsl:when test=".//ali:license_ref">
                            <xsl:attribute name="xlink:href"><xsl:value-of select=".//ali:license_ref"/></xsl:attribute>
                        </xsl:when>
                    </xsl:choose>
                    <xsl:value-of select="normalize-space(license-p|p)"/>
                </mods:accessCondition>
            </xsl:for-each>

            <!-- Funding -->
            <xsl:for-each select="//funding-statement">
                <mods:note type="funding">
                    <xsl:value-of select="normalize-space()" />
                </mods:note>
            </xsl:for-each>

            <xsl:for-each select="//article-meta/funding-group/award-group/funding-source">
                <mods:note type="funding">
                    <xsl:value-of select="normalize-space()" />
                </mods:note>
            </xsl:for-each>

        </mods:mods>

    </xsl:template>

    <xsl:template name="compose-date">
        <xsl:value-of select="year"/>
        <xsl:variable name="mnth" select="month"/>
        <!-- check if month is a number -->
        <xsl:choose>
            <xsl:when test="number(month) = month">
                <xsl:text>-</xsl:text>
                <xsl:value-of select="format-number(month,'00')"/>
            </xsl:when>
            <xsl:when test="document('')//monthNameMap/monthNames[@text=$mnth]/@number">
                <xsl:text>-</xsl:text>
                <xsl:value-of select="document('')//monthNameMap/monthNames[@text=$mnth]/@number"/>
            </xsl:when>
            <xsl:otherwise>
                <xsl:text>-12</xsl:text>
            </xsl:otherwise>
        </xsl:choose>
        <xsl:if test="day">
            <xsl:text>-</xsl:text>
            <xsl:value-of select="format-number(day,'00')"/>
        </xsl:if>
    </xsl:template>

    <xsl:template name="insert-lang-attribute">
        <xsl:choose>
        <xsl:when test="@xml:lang">
            <xsl:attribute name="xml:lang"><xsl:value-of select="@xml:lang"/></xsl:attribute>
        </xsl:when>
        <xsl:when test="../@xml:lang">
            <xsl:attribute name="xml:lang"><xsl:value-of select="../@xml:lang"/></xsl:attribute>
        </xsl:when>
        </xsl:choose>
    </xsl:template>

    <xsl:template name="abstract-nested-whitespacing">
    <!-- this template transforms abstract content to normalize whitespacing between child elements.
    if abstract contains sub elements, it likely contains chemical formulas and the text contents will be used as is.
    Otherwise, this template deliberately adds white spaces between the text contents of each child element. If the current element is a title element, line breaks will be added before and after the current text to improve readability and approximate intended document structure. -->
      <xsl:choose>
      <xsl:when test="descendant::sub">
        <xsl:for-each select="descendant-or-self::text()">
          <xsl:if test="string-length(normalize-space())&gt;0">
            <xsl:choose>
              <xsl:when test="local-name(parent::*) = 'tex-math'">
              <!--ignore tex-math elements-->
              </xsl:when>
              <xsl:otherwise>
                <xsl:value-of select="."/>
              </xsl:otherwise>
            </xsl:choose>
          </xsl:if>
        </xsl:for-each>
      </xsl:when>
      <xsl:otherwise>
        <xsl:for-each select="descendant-or-self::text()">
          <xsl:if test="string-length(normalize-space())&gt;0">
            <xsl:choose>
              <xsl:when test="local-name(parent::*)='title' ">
                <!-- when text of title element is selected, add line breaks before and after-->
                <xsl:text>
                </xsl:text>
                <xsl:value-of select="normalize-space()"/>
                <xsl:text>
                </xsl:text>
              </xsl:when>
              <xsl:when test="local-name(parent::*) = 'tex-math'">
              </xsl:when>
              <xsl:when test="contains(name(parent::*),'mml:')">
                <xsl:value-of select="."/>
              </xsl:when>
              <xsl:otherwise> <!--otherwise select space-normalized text and add a whitespace afterward-->
                <xsl:value-of select="normalize-space()"/>
                <xsl:text> </xsl:text>
              </xsl:otherwise>
            </xsl:choose>
          </xsl:if>
        </xsl:for-each>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <xsl:template name="build_aff_string">
  <!-- builds string recursively, by going through each node and adding its text to the string. end condition: counter > total no of nodes. -->
        <xsl:param name="combined_string"/>
        <xsl:param name="aff_node"/>
        <xsl:param name="current_position"/>
        <xsl:variable name="total_nodes" select="count($aff_node/descendant-or-self::text())"/>
        <xsl:choose>
            <xsl:when test="number($current_position) &gt; $total_nodes">
                <!-- exit condition, prints out value of combined_string -->
                <xsl:value-of select="$combined_string"/>
            </xsl:when>
            <xsl:otherwise>
            <xsl:for-each select="$aff_node/descendant-or-self::text()[$current_position]">
            <!--selects current node-->
                <xsl:variable name="stripped_string" select="normalize-space()"/>
                <xsl:choose>
                    <xsl:when test="local-name(parent::*)='sub' or local-name(parent::*)='label' or local-name(parent::*) = 'sup' or local-name(parent::*)='email' or local-name(parent::*)='institution-id' or local-name(parent::*)='postal-code'">
                    <!-- if text belongs to irrelevant element, simply call template again with counter +1 -->
                            <xsl:call-template name="build_aff_string">
                                <xsl:with-param name="combined_string" select="$combined_string"/>
                                <xsl:with-param name="aff_node" select="$aff_node"/>
                                <xsl:with-param name="current_position" select="number($current_position)+1"/>
                            </xsl:call-template>
                    </xsl:when>
                    <xsl:when test="string-length($stripped_string) &gt; 0 and
                    $stripped_string != ',' and
                    $stripped_string != '.' and
                    $stripped_string != ';'">
                    <!-- if stripped_string is not empty and not only a punctuation character -->
                        <xsl:choose>
                            <xsl:when test="string-length($combined_string) &gt; 0"> <!-- if there is already text in the combined string, add stripped_string with separators depending on preceding / succeeding punctuation -->
                                <xsl:variable name="last_char" select="substring($combined_string, string-length($combined_string))"/>
                                <xsl:variable name="first_char" select="substring($stripped_string, 1,1)"/>
                                <xsl:choose>
                                    <xsl:when test="$last_char = ',' or $last_char = '.' or $last_char = ';'"> <!-- if there's a separator at the end of the combined string -->
                                        <xsl:variable name="edited_string" select="concat($combined_string,' ', $stripped_string)"/>
                                        <xsl:call-template name="build_aff_string">
                                            <xsl:with-param name="combined_string" select="$edited_string"/>
                                            <xsl:with-param name="aff_node" select="$aff_node"/>
                                            <xsl:with-param name="current_position" select="number($current_position)+1"/>
                                        </xsl:call-template>
                                    </xsl:when>
                                    <xsl:when test="$first_char = ',' or $first_char = '.' or $first_char = ';'"> <!-- if there's a separator at the start of the new string -->
                                        <xsl:variable name="edited_string" select="concat($combined_string, $stripped_string)"/>
                                        <xsl:call-template name="build_aff_string">
                                            <xsl:with-param name="combined_string" select="$edited_string"/>
                                            <xsl:with-param name="aff_node" select="$aff_node"/>
                                            <xsl:with-param name="current_position" select="number($current_position)+1"/>
                                        </xsl:call-template>
                                    </xsl:when>
                                    <xsl:otherwise> <!-- normal case: add to combined_string with ', ' as separator -->
                                        <xsl:variable name="edited_string" select="concat($combined_string,', ', $stripped_string)"/>
                                        <xsl:call-template name="build_aff_string">
                                            <xsl:with-param name="combined_string" select="$edited_string"/>
                                            <xsl:with-param name="aff_node" select="$aff_node"/>
                                            <xsl:with-param name="current_position" select="number($current_position)+1"/>
                                        </xsl:call-template>
                                    </xsl:otherwise>
                                </xsl:choose>
                            </xsl:when>
                            <xsl:otherwise>
                            <!-- if combined_string is empty, then set stripped_string as combined_string and call template again. -->
                                <xsl:call-template name="build_aff_string">
                                <xsl:with-param name="combined_string" select="$stripped_string"/>
                                <xsl:with-param name="aff_node" select="$aff_node"/>
                                <xsl:with-param name="current_position" select="number($current_position)+1"/>
                                </xsl:call-template>
                            </xsl:otherwise>
                        </xsl:choose>
                    </xsl:when>
                    <xsl:otherwise>
                        <!-- if stripped_string is either empty or contains only punctuation, call template again with counter +1 -->
                        <xsl:call-template name="build_aff_string">
                            <xsl:with-param name="combined_string" select="$combined_string"/>
                            <xsl:with-param name="aff_node" select="$aff_node"/>
                            <xsl:with-param name="current_position" select="number($current_position)+1"/>
                        </xsl:call-template>
                    </xsl:otherwise>
                </xsl:choose>
                </xsl:for-each>
            </xsl:otherwise>
        </xsl:choose>
    </xsl:template>

    <xsl:template name="parse-multiple-rids-for-affs">
        <xsl:param name="rid_string"/>
        <!-- Template recursively parses the affiliation rids contained in contrib elements. Copernicus flavor.
        i.e. <contrib ... rid="aff1 aff2"/>
        -->
        <xsl:choose>
        <xsl:when test="contains($rid_string,' ')">
            <mods:affiliation xmlns:mods="http://www.loc.gov/mods/v3">
            <xsl:call-template name="build_aff_string">
                <xsl:with-param name="aff_node" select="key('kAffById', substring-before($rid_string, ' '))"/>
                <xsl:with-param name="combined_string" select="''"/>
                <xsl:with-param name="current_position" select="1"/>
            </xsl:call-template>
            </mods:affiliation>
            <xsl:call-template name="parse-multiple-rids-for-affs">
                <xsl:with-param name="rid_string" select="substring-after($rid_string,' ')"/>
            </xsl:call-template>
        </xsl:when>
        <xsl:otherwise>
            <mods:affiliation xmlns:mods="http://www.loc.gov/mods/v3">
            <xsl:call-template name="build_aff_string">
                <xsl:with-param name="aff_node" select="key('kAffById', $rid_string)"/>
                <xsl:with-param name="combined_string" select="''"/>
                <xsl:with-param name="current_position" select="1"/>
            </xsl:call-template>
            </mods:affiliation>
        </xsl:otherwise>
        </xsl:choose>
  </xsl:template>


</xsl:stylesheet>
  '''.format(xmlinject=mnth2number)



  # 2017-04-20 TD : static(!!) strings containing the xsl code RSC --> OPUS4
  #                 Note that there MUST NOT be any kind of '<?xml ...?>' header!
  #
  # 2017-07-12 TD : Some (beautifying?) bug fixes such as translating names of months
  #
  # 2019-08-13 TD : Change of the output "issn" in the tag "identifiers": no distinction 
  #                 between eISSN and pISSN anymore! In fact, OPUS4 article data model 
  #                 does not support these subtypes as identifier.
  #
  rsc2opus4 = '''
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

  <!-- <xsl:import href="outputTokens.xsl"/> -->
  <xsl:output method="xml" omit-xml-declaration="yes" indent="yes" encoding="utf-8"/>

  <xsl:variable name="inject2">
    {xmlinject2}
  </xsl:variable>
  <xsl:variable name="inject1">
    {xmlinject1}
  </xsl:variable>
  <xsl:variable name="langIn" select="translate(/article/@xml:lang,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"/>
  <!-- <xsl:variable name="langOut">eng</xsl:variable> -->
  <xsl:variable name="langOut" select="document('')//langCodeMap/langCodes[@iso639-1=$langIn]/@iso639-2"/>

  <xsl:template match="/">
  <import>
    <opusDocument>
          <xsl:attribute name="language"> 
            <xsl:value-of select="$langOut"/>
          </xsl:attribute>
          <xsl:attribute name="type">
            <xsl:text>article</xsl:text>
          </xsl:attribute>
          <xsl:if test="//published[@type='print']/pubfront/fpage">
            <xsl:attribute name="pageFirst">
              <xsl:value-of select="//published[@type='print']/pubfront/fpage"/>
            </xsl:attribute>
          </xsl:if>
          <xsl:if test="//published[@type='print']/pubfront/lpage">
            <xsl:attribute name="pageLast">
              <xsl:value-of select="//published[@type='print']/pubfront/lpage"/>
            </xsl:attribute>
          </xsl:if>
          <xsl:if test="//published[@type='print']/volumeref/link">
            <xsl:attribute name="volume">
              <xsl:value-of select="//published[@type='print']/volumeref/link"/>
            </xsl:attribute>
          </xsl:if>
          <xsl:if test="//published[@type='print']/issueref/link">
            <xsl:attribute name="issue">
              <xsl:value-of select="//published[@type='print']/issueref/link"/>
            </xsl:attribute>
          </xsl:if>
          <xsl:attribute name="publisherName">
            <xsl:for-each select="//published[@type='print']/journalref/publisher/orgname/nameelt">
              <xsl:value-of select="normalize-space(text())"/>
              <xsl:if test="position() != last()">
                <xsl:text>, </xsl:text>
              </xsl:if>
            </xsl:for-each>
          </xsl:attribute>
          <!--
          <xsl:if test="//publisher//publisher-loc">
            <xsl:attribute name="publisherPlace">
              <xsl:value-of select="//publisher//publisher-loc"/>
            </xsl:attribute>
          </xsl:if>
          -->
          <xsl:attribute name="belongsToBibliography">
            <xsl:text>false</xsl:text>
          </xsl:attribute>
          <xsl:attribute name="serverState">
            <xsl:text>unpublished</xsl:text>
          </xsl:attribute>
          <!-- 
          language="eng"
          type="article|bachelorthesis|bookpart|book|conferenceobject|contributiontoperiodical|coursematerial|diplom|doctoralthesis|examen|habilitation|image|lecture|magister|masterthesis|movingimage|other|periodical|preprint|report|review|studythesis|workingpaper"
          pageFirst=""
          pageLast=""
          pageNumber=""
          edition=""
          volume=""
          issue=""
          publisherName=""
          publisherPlace=""
          creatingCorporation=""
          contributingCorporation=""
          belongsToBibliography="true|false"
          serverState="audited|published|restricted|inprogress|unpublished"
          -->
      <titlesMain>
          <titleMain>
            <xsl:attribute name="language"><xsl:value-of select="$langOut"/></xsl:attribute>
            <xsl:value-of select="//art-front/titlegrp/title"/>
          </titleMain>
      </titlesMain>
      <titles>
          <xsl:if test="//published[@type='print']/journalref/title[@type='full']">
            <title> 
              <xsl:attribute name="language"><xsl:value-of select="$langOut"/></xsl:attribute>
              <xsl:attribute name="type"><xsl:text>parent</xsl:text></xsl:attribute> 
              <xsl:value-of select="//published[@type='print']/journalref/title"/>
            </title>
          </xsl:if>
      </titles>
      <abstracts>
          <xsl:if test="//art-front/abstract">
            <abstract>
              <xsl:attribute name="language"><xsl:value-of select="$langOut"/></xsl:attribute>
              <xsl:value-of select="//art-front/abstract"/>
            </abstract>
          </xsl:if>
      </abstracts>
      <persons>
          <xsl:for-each select="//art-front/authgrp/author">
            <xsl:if test="person/persname/surname">
            <person>
                <xsl:attribute name="role"><xsl:text>author</xsl:text></xsl:attribute>
                <xsl:attribute name="firstName"><xsl:copy-of select="person/persname/fname/text()"/></xsl:attribute>
                <xsl:attribute name="lastName"><xsl:copy-of select="person/persname/surname/text()"/></xsl:attribute>
                <!--
                role="advisor|author|contributor|editor|referee|translator|submitter|other"
                firstName=""
                lastName=""
                academicTitle=""
                email=""
                allowEmailContact="true|false"
                placeOfBirth=""
                dateOfBirth="1999-12-31"
                -->
                <!--
                <identifiers>
                  <identifier type="orcid|gnd|intern">?????</identifier>
                </identifiers>
                -->
            </person>
            </xsl:if>
          </xsl:for-each>
      </persons>
      <keywords>
          <keyword> 
            <xsl:attribute name="language"><xsl:value-of select="$langOut"/></xsl:attribute>
            <xsl:attribute name="type"><xsl:text>swd</xsl:text></xsl:attribute>
            <xsl:text>-</xsl:text>
          </keyword>
      </keywords>
      <!--
      <dnbInstitutions>
          <dnbInstitution id="<integer>" role="grantor|publisher"/>
      </dnbInstitutions>
      -->
      <dates>
          <xsl:for-each select="//published[@type='web']/pubfront/date">
          <xsl:if test="position() = last()">
            <xsl:variable name="mnth" select="month"/>
            <date>
              <xsl:attribute name="type"><xsl:text>published</xsl:text></xsl:attribute>
              <xsl:attribute name="monthDay">
                <xsl:text>--</xsl:text>
                <xsl:choose>
                  <xsl:when test="format-number(month,'00')!='NaN'">
                    <xsl:value-of select="format-number(month,'00')"/>
                  </xsl:when>
                  <xsl:when test="document('')//monthNameMap/monthNames[@text=$mnth]/@number">
                    <xsl:value-of select="document('')//monthNameMap/monthNames[@text=$mnth]/@number"/>
                  </xsl:when>
                  <xsl:otherwise>
                    <xsl:text>12</xsl:text>
                  </xsl:otherwise>
                </xsl:choose>
                <xsl:text>-</xsl:text>
                <xsl:choose>
                  <xsl:when test="format-number(day,'00')!='NaN'">
                     <xsl:value-of select="format-number(day,'00')"/>
                  </xsl:when>
                  <xsl:otherwise>
                     <xsl:text>01</xsl:text>
                  </xsl:otherwise>
                </xsl:choose>
              </xsl:attribute>
              <xsl:attribute name="year">
                <xsl:value-of select="year"/>
              </xsl:attribute>
            </date>
          </xsl:if>
          </xsl:for-each>
      </dates>
      <identifiers>
        <xsl:for-each select="//published[@type='print']/journalref/issn[@type='print']">
          <identifier>
            <xsl:attribute name="type"><xsl:text>issn</xsl:text></xsl:attribute>
            <xsl:value-of select="normalize-space(text())"/>
          </identifier>
        </xsl:for-each>
        <xsl:for-each select="//published[@type='print']/journalref/issn[@type='online']">
          <identifier>
            <xsl:attribute name="type"><xsl:text>issn</xsl:text></xsl:attribute>
            <xsl:value-of select="normalize-space(text())"/>
          </identifier>
        </xsl:for-each>
        <xsl:if test="//art-admin/doi">
          <identifier>
            <xsl:attribute name="type"><xsl:text>doi</xsl:text></xsl:attribute>
            <xsl:value-of select="//art-admin/doi"/>
          </identifier>
        </xsl:if>
      </identifiers>
      <!--
      <identifiers>
          <identifier>
             <xsl:attribute name="type"><xsl:text>issn</xsl:text></xsl:attribute>
             <xsl:for-each select="//published[@type='print']/journalref/issn[@type='print']">
                <xsl:value-of select="normalize-space(text())"/>
                <xsl:if test="position() != last()">
                   <xsl:text> , </xsl:text>
                </xsl:if>
                <xsl:if test="position() = last()">
                   <xsl:text> (pISSN)</xsl:text>
                </xsl:if>
             </xsl:for-each>
             <xsl:if test="//published[@type='print']/journalref/issn[@type='online']">
                <xsl:text> ; </xsl:text>
                <xsl:for-each select="//published[@type='print']/journalref/issn[@type='online']">
                   <xsl:value-of select="normalize-space(text())"/>
                   <xsl:if test="position() != last()">
                      <xsl:text> , </xsl:text>
                   </xsl:if>
                   <xsl:if test="position() = last()">
                      <xsl:text> (eISSN)</xsl:text>
                   </xsl:if>
                </xsl:for-each>
             </xsl:if>
          </identifier>
          <identifier>
             <xsl:attribute name="type"><xsl:text>doi</xsl:text></xsl:attribute>
             <xsl:value-of select="//art-admin/doi"/>
          </identifier>
      </identifiers>
      -->
      <!--
      <notes>
          <note visibility="private|public">?????</note>
      </notes>
      <collections>
          <collection id="<integer>"/>
      </collections>
      <series>
          <seriesItem id="<integer>" number=""/>
      </series>
      <enrichments>
          <enrichment key="">?????</enrichment>
      </enrichments>
      <licences>
          <licence id="<integer>"/>
      </licences>
      <files basedir="">
          <file 
                path=""
                name=""
                language=""
                displayName=""
                visibleInOai="true|false"
                visibleInFrontdoor="true|false"
                sortOrder="<int>">
            <comment>?????</comment>
            <checksum type="md5|sha256|sha512">?????</checksum>
          </file>
      </files>
      -->
    </opusDocument>
  </import>
  </xsl:template>

</xsl:stylesheet>
  '''.format(xmlinject1=iso639codes,xmlinject2=mnth2number)


  # 2017-05-15 TD : static string containing the xsl code for RSC --> ESciDoc
  #                 Note that there MUST NOT be any kind of '<?xml ...?>' header!
  #
  # 2017-07-12 TD : Some (beautifying?) bug fixes such as translating names of months
  #
  rsc2escidoc = '''
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

  <xsl:output method="xml" indent="yes" encoding="UTF-8"/>

  <xsl:param name="contentmodel"><xsl:text>escidoc:persistent4</xsl:text></xsl:param>

  <xsl:variable name="inject2">
    {xmlinject2}
  </xsl:variable>
  <xsl:variable name="inject1">
    {xmlinject1}
  </xsl:variable>
  <xsl:variable name="langIn" select="translate(/article/@xml:lang,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"/>
  <xsl:variable name="langOut" select="document('')//langCodeMap/langCodes[@iso639-1=$langIn]/@iso639-3"/>

  <!--
  <xsl:key name="kAffById" match="//art-front/aff" use="@id"/>

  <xsl:template name="split">
     <xsl:param name="pText" select="."/>
     <xsl:if test="string-length($pText)">
        <xsl:if test="not($pText=.)">
        </xsl:if>
        <xsl:value-of select="substring-before(concat($pText,' '),' ')"/>
        <xsl:call-template name="split">
           <xsl:with-param name="pText" select="substring-after($pText,' ')"/>
        </xsl:call-template>
     </xsl:if>
  </xsl:template>
  -->

  <xsl:template match="/">
  <escidocItem:item xmlns:escidocContext="http://www.escidoc.de/schemas/context/0.7"
    xmlns:escidocContextList="http://www.escidoc.de/schemas/contextlist/0.7"
    xmlns:escidocComponents="http://www.escidoc.de/schemas/components/0.9"
    xmlns:escidocItem="http://www.escidoc.de/schemas/item/0.10"
    xmlns:escidocItemList="http://www.escidoc.de/schemas/itemlist/0.10"
    xmlns:escidocMetadataRecords="http://www.escidoc.de/schemas/metadatarecords/0.5"
    xmlns:escidocRelations="http://www.escidoc.de/schemas/relations/0.3"
    xmlns:escidocSearchResult="http://www.escidoc.de/schemas/searchresult/0.8"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:prop="http://escidoc.de/core/01/properties/"
    xmlns:srel="http://escidoc.de/core/01/structural-relations/"
    xmlns:version="http://escidoc.de/core/01/properties/version/"
    xmlns:release="http://escidoc.de/core/01/properties/release/"
    xmlns:member-list="http://www.escidoc.de/schemas/memberlist/0.10"
    xmlns:container="http://www.escidoc.de/schemas/container/0.9"
    xmlns:container-list="http://www.escidoc.de/schemas/containerlist/0.9"
    xmlns:struct-map="http://www.escidoc.de/schemas/structmap/0.4"
    xmlns:mods-md="http://www.loc.gov/mods/v3"
    xmlns:file="http://purl.org/escidoc/metadata/profiles/0.1/file"
    xmlns:publication="http://purl.org/escidoc/metadata/profiles/0.1/publication"
    xmlns:yearbook="http://purl.org/escidoc/metadata/profiles/0.1/yearbook"
    xmlns:face="http://purl.org/escidoc/metadata/profiles/0.1/face"
    xmlns:jhove="http://hul.harvard.edu/ois/xml/ns/jhove">
      <escidocItem:properties>
        <srel:content-model>
          <xsl:attribute name="objid"><xsl:value-of select="$contentmodel"/></xsl:attribute>
        </srel:content-model>
        <prop:content-model-specific xmlns:prop="http://escidoc.de/core/01/properties/"/> 
      </escidocItem:properties>
      <escidocMetadataRecords:md-records>
        <escidocMetadataRecords:md-record>
          <xsl:attribute name="name"><xsl:text>escidoc</xsl:text></xsl:attribute>
          <publication:publication xmlns:dc="http://purl.org/dc/elements/1.1/"
            xmlns:dcterms="http://purl.org/dc/terms/"
            xmlns:eterms="http://purl.org/escidoc/metadata/terms/0.1/"
            xmlns:person="http://purl.org/escidoc/metadata/profiles/0.1/person" 
            xmlns:event="http://purl.org/escidoc/metadata/profiles/0.1/event" 
            xmlns:source="http://purl.org/escidoc/metadata/profiles/0.1/source" 
            xmlns:organization="http://purl.org/escidoc/metadata/profiles/0.1/organization" 
            xmlns:legalCase="http://purl.org/escidoc/metadata/profiles/0.1/legal-case"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <xsl:attribute name="type"><xsl:text>http://purl.org/escidoc/metadata/ves/publication-types/article</xsl:text></xsl:attribute>
            <xsl:for-each select="//art-front/authgrp/author">
              <eterms:creator>
                <xsl:attribute name="role">
                  <xsl:text>http://www.loc.gov/loc.terms/relators/AUT</xsl:text>
                </xsl:attribute>
                <person:person>
                  <eterms:family-name><xsl:copy-of select="person/persname/surname/text()"/></eterms:family-name>
                  <eterms:given-name><xsl:copy-of select="person/persname/fname/text()"/></eterms:given-name>
                      <xsl:choose>
                        <xsl:when test="string-length(./@aff)!=0">
                          <xsl:variable name="affs" select="./@aff"/>
                          <xsl:for-each select="//art-front/authgrp/aff[contains($affs,@id)]">
                             <organization:organization>
                               <dc:title>
                                 <xsl:for-each select="org/orgname/nameelt">
                                    <xsl:value-of select="normalize-space(text())"/>
                                    <xsl:if test="position() != last()">
                                       <xsl:text>, </xsl:text>
                                    </xsl:if>
                                 </xsl:for-each>
                               </dc:title>
                               <eterms:address>
                                 <xsl:for-each select="address/addrelt">
                                    <xsl:value-of select="normalize-space(text())"/>
                                    <xsl:if test="position() != last()">
                                       <xsl:text>, </xsl:text>
                                    </xsl:if>
                                 </xsl:for-each>
                                 <xsl:if test="address/city">
                                    <xsl:if test="string-length(address/addrelt[position()=last()]/text())!=0">
                                       <xsl:text>, </xsl:text>
                                    </xsl:if>
                                    <xsl:value-of select="normalize-space(address/city/text())"/>
                                 </xsl:if>
                                 <xsl:if test="address/country">
                                    <xsl:if test="string-length(address/addrelt[position()=last()]/text())!=0 or string-length(address/city/text())!=0">
                                       <xsl:text>, </xsl:text>
                                    </xsl:if>
                                    <xsl:value-of select="normalize-space(address/country/text())"/>
                                 </xsl:if>
                               </eterms:address>
                               <!--
                               <eterms:address><xsl:copy-of select="key('kAffById', @rid)/text()"/></eterms:address>
                               <dc:title><xsl:value-of select="key('kAffById', @rid)/text()[normalize-space()][1]"/></dc:title>
                               -->
                               <!-- for an explanation of the last select expression see 
                                    http://stackoverflow.com/questions/16134646/how-to-return-text-of-node-without-child-nodes-text
                                    the solved problem here is to get rid of the footnote markers inside the affiliation texts that are often given by child nodes...
                                -->
                             </organization:organization>
                          </xsl:for-each> 
                        </xsl:when>
                        <xsl:otherwise>
                           <organization:organization>
                             <dc:title><xsl:text>-</xsl:text></dc:title> 
                             <eterms:address><xsl:text>-</xsl:text></eterms:address>
                           </organization:organization>
                        </xsl:otherwise>
                      </xsl:choose>
                  <!--
                  <organization:organization>
                    <dc:title></dc:title>
                    <eterms:address/>
                  </organization:organization>
                  -->
                </person:person>
              </eterms:creator>
            </xsl:for-each>
            <dc:title><xsl:value-of select="//art-front/titlegrp/title"/></dc:title>
            <dc:language>
              <xsl:attribute name="xsi:type"><xsl:text>dcterms:ISO639-3</xsl:text></xsl:attribute>
              <xsl:value-of select="$langOut"/>
            </dc:language>
            <dc:identifier>
              <xsl:attribute name="xsi:type"><xsl:text>eterms:DOI</xsl:text></xsl:attribute>
              <xsl:value-of select="//art-admin/doi"/>
            </dc:identifier>
            <!--
            <xsl:if test="//article-meta/article-id[@pub-id-type='pmid']">
              <dc:identifier>
                <xsl:attribute name="xsi:type"><xsl:text>eterms:PMID</xsl:text></xsl:attribute>
                <xsl:value-of select="//article-meta/article-id[@pub-id-type='pmid']"/>
              </dc:identifier>
            </xsl:if>
            -->
            <dcterms:issued>
              <xsl:attribute name="xsi:type"><xsl:text>dcterms:W3CDTF</xsl:text></xsl:attribute>
              <xsl:choose>
                <xsl:when test="//published[@type='web']/pubfront/date/year">
                  <xsl:call-template name="compose-date">
                    <xsl:with-param name="xpub" select="'web'"/>
                  </xsl:call-template>
                </xsl:when>
                <xsl:when test="//published[@type='print']/pubfront/date/year">
                  <xsl:call-template name="compose-date">
                    <xsl:with-param name="xpub" select="'print'"/>
                  </xsl:call-template>
                </xsl:when>
                <xsl:otherwise>
                  <xsl:text>1111-11-11</xsl:text>
                </xsl:otherwise>
              </xsl:choose>
            </dcterms:issued>
            <source:source>
              <xsl:attribute name="type"><xsl:text>http://purl.org/escidoc/metadata/ves/publication-types/journal</xsl:text></xsl:attribute>
              <dc:title><xsl:value-of select="//published[@type='print']/journalref/title[@type='full']"/></dc:title>
              <eterms:volume><xsl:value-of select="//published[@type='print']/volumeref/link"/></eterms:volume>
              <eterms:issue><xsl:value-of select="//published[@type='print']/issueref/link"/></eterms:issue>
              <eterms:start-page><xsl:value-of select="//published[@type='print']/pubfront/fpage"/></eterms:start-page>
              <eterms:end-page><xsl:value-of select="//published[@type='print']/pubfront/lpage"/></eterms:end-page>
              <eterms:total-number-of-pages><xsl:value-of select="//published[@type='print']/pubfront/no-of-pages"/></eterms:total-number-of-pages>
              <eterms:publishing-info>
                <dc:publisher><xsl:value-of select="//published[@type='print']/journalref/publisher/orgname/nameelt"/></dc:publisher>
                <!--
                <eterms:place><xsl:value-of select="//published[@type='print']/publisher//orgname/locelt"/></eterms:place>
                -->
              </eterms:publishing-info>
              <xsl:if test="//published[@type='print']/journalref/issn[@type='print']">
                <dc:identifier>
                  <xsl:attribute name="xsi:type"><xsl:text>eterms:ISSN</xsl:text></xsl:attribute>
                  <xsl:value-of select="//published[@type='print']/journalref/issn[@type='print']"/><xsl:text> (pISSN)</xsl:text>
                </dc:identifier>
              </xsl:if>
              <xsl:if test="//published[@type='print']/journalref/issn[@type='online']">
                <dc:identifier>
                  <xsl:attribute name="xsi:type"><xsl:text>eterms:ISSN</xsl:text></xsl:attribute>
                  <xsl:value-of select="//published[@type='print']/journalref/issn[@type='online']"/><xsl:text> (eISSN)</xsl:text>
                </dc:identifier>
              </xsl:if>
            </source:source>
            <dcterms:abstract><xsl:value-of select="//art-front/abstract"/></dcterms:abstract>
            <dcterms:subject><xsl:text>-</xsl:text></dcterms:subject>
            <dc:subject>
              <xsl:attribute name="xsi:type"><xsl:text>eterms:DDC</xsl:text></xsl:attribute>
            </dc:subject>
          </publication:publication>
        </escidocMetadataRecords:md-record>
      </escidocMetadataRecords:md-records>
    </escidocItem:item>
  </xsl:template>

  <xsl:template name="compose-date">
    <xsl:param name="xpub" select="'web'"/>
    <xsl:for-each select="//published[@type=$xpub]/pubfront/date">
      <xsl:if test="position() = last()">
        <xsl:variable name="mnth" select="month"/>
        <xsl:value-of select="year"/>
        <xsl:text>-</xsl:text>
        <xsl:choose>
          <xsl:when test="format-number(month,'00')!='NaN'">
            <xsl:value-of select="format-number(month,'00')"/>
          </xsl:when>
          <xsl:when test="document('')//monthNameMap/monthNames[@text=$mnth]/@number">
            <xsl:value-of select="document('')//monthNameMap/monthNames[@text=$mnth]/@number"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:text>12</xsl:text>
          </xsl:otherwise>
        </xsl:choose>
        <xsl:if test="format-number(day,'00')!='NaN'">
          <xsl:text>-</xsl:text>
          <xsl:value-of select="format-number(day,'00')"/>
        </xsl:if>
      </xsl:if>
    </xsl:for-each>
  </xsl:template>

</xsl:stylesheet>
  '''.format(xmlinject1=iso639codes,xmlinject2=mnth2number)


  # 2017-05-15 TD : static string containing the xsl code for RSC --> METSDspaceSIP
  #                 Note that there MUST NOT be any kind of '<?xml ...?>' header!
  #
  # 2017-07-12 TD : Some (beautifying?) bug fixes such as translating names of months
  #
  rsc2metsdspace = '''
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

  <!-- <xsl:import href="outputTokens.xsl"/> -->
  <xsl:output method="xml" omit-xml-declaration="no" standalone="no" indent="yes" encoding="utf-8"/>

  <xsl:param name="currdatetime">1970-01-01T00:00:00</xsl:param>

  <xsl:variable name="inject2">
    {xmlinject2}
  </xsl:variable>
  <xsl:variable name="inject1">
    {xmlinject1}
  </xsl:variable>
  <xsl:variable name="langIn" select="translate(/article/@xml:lang,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"/>
  <!-- <xsl:variable name="langOut">eng</xsl:variable> -->
  <xsl:variable name="langOut" select="document('')//langCodeMap/langCodes[@iso639-1=$langIn]/@iso639-2"/>

  <xsl:template match="/">
  <mets xmlns="http://www.loc.gov/METS/"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.loc.gov/METS/ http://www.loc.gov/standards/mets/mets.xsd">
    <xsl:attribute name="ID"><xsl:text>sword-mets_mets</xsl:text></xsl:attribute>
    <xsl:attribute name="OBJID"><xsl:text>sword-mets</xsl:text></xsl:attribute>
    <xsl:attribute name="LABEL"><xsl:text>DSpace SWORD Item</xsl:text></xsl:attribute>
    <xsl:attribute name="PROFILE"><xsl:text>DSpace METS SIP Profile 1.0</xsl:text></xsl:attribute>
    <metsHdr>
      <xsl:attribute name="CREATEDATE"><xsl:value-of select="$currdatetime"/></xsl:attribute>
      <agent>
        <xsl:attribute name="ROLE">CUSTODIAN</xsl:attribute>
        <xsl:attribute name="TYPE">ORGANIZATION</xsl:attribute>
        <name>DeepGreen</name>
      </agent>
    </metsHdr>
    <dmdSec>
      <xsl:attribute name="ID">sword-mets-dmd-1</xsl:attribute>
      <xsl:attribute name="GROUPID">sword-mets-dmd-1_group-1</xsl:attribute>
      <mdWrap>
        <xsl:attribute name="LABEL"><xsl:text>SWAP Metadata</xsl:text></xsl:attribute>
        <xsl:attribute name="MDTYPE">OTHER</xsl:attribute>
        <xsl:attribute name="OTHERMDTYPE">EPDCX</xsl:attribute>
        <xsl:attribute name="MIMETYPE"><xsl:text>text/xml</xsl:text></xsl:attribute>
        <xmlData>
          <epdcx:descriptionSet xmlns:epdcx="http://purl.org/eprint/epdcx/2006-11-16/"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://purl.org/eprint/epdcx/2006-11-16/ http://purl.org/eprint/epdcx/xsd/2006-11-16/epdcx.xsd">
            <epdcx:description>
              <xsl:attribute name="epdcx:resourceId">sword-mets-epdcx-1</xsl:attribute>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/elements/1.1/type</xsl:attribute>
                <xsl:attribute name="epdcx:valueURI">http://purl.org/eprint/entityType/ScholarlyWork</xsl:attribute>
              </epdcx:statement>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/elements/1.1/title</xsl:attribute>
                <epdcx:valueString><xsl:value-of select="//art-front/titlegrp/title"/></epdcx:valueString>
              </epdcx:statement>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/terms/abstract</xsl:attribute>
                <epdcx:valueString><xsl:value-of select="//art-front/abstract"/></epdcx:valueString>
              </epdcx:statement>
              <xsl:for-each select="//art-front/authgrp/author">
                <epdcx:statement>
                  <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/elements/1.1/creator</xsl:attribute>
                  <epdcx:valueString>
                    <xsl:copy-of select="person/persname/surname/text()"/>
                    <xsl:if test="string-length(person/persname/fname/text()) > 0">
                      <xsl:text>, </xsl:text>
                      <xsl:copy-of select="person/persname/fname/text()"/>
                    </xsl:if>
                  </epdcx:valueString>
                </epdcx:statement>
              </xsl:for-each>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/elements/1.1/identifier</xsl:attribute>
                <epdcx:valueString>
                  <xsl:attribute name="epdcx:sesURI">http://purl.org/dc/terms/URI</xsl:attribute>
                  <xsl:text>http://dx.doi.org/</xsl:text>
                  <xsl:value-of select="//art-admin/doi"/>
                </epdcx:valueString>
              </epdcx:statement>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/eprint/terms/isExpressedAs</xsl:attribute>
                <xsl:attribute name="epdcx:valueRef">sword-mets-expr-1</xsl:attribute>
              </epdcx:statement>
            </epdcx:description>
            <!-- Second (level?) description starts here -->
            <epdcx:description>
              <xsl:attribute name="epdcx:resourceId">sword-mets-expr-1</xsl:attribute>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/elements/1.1/type</xsl:attribute>
                <xsl:attribute name="epdcx:valueURI">http://purl.org/eprint/entityType/Expression</xsl:attribute>
              </epdcx:statement>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/terms/bibliographicCitation</xsl:attribute>
                <epdcx:valueString>
                  <xsl:copy-of select="//art-front/authgrp/author[position()=1]/person/persname/surname/text()"/>
                  <xsl:if test="string-length(//art-front/authgrp/author[position()=1]/person/persname/fname/text()) > 0">
                    <xsl:text>, </xsl:text>
                    <xsl:copy-of select="//art-front/authgrp/author[position()=1]/person/persname/fname/text()"/>
                  </xsl:if>
                  <xsl:if test="//art-front/authgrp/author[position()>1]">
                    <xsl:text> et al.</xsl:text>
                  </xsl:if>
                  <xsl:text>: </xsl:text>
                  <xsl:value-of select="//published[@type='print']/journalref/title"/>
                  <xsl:text> </xsl:text>
                  <xsl:value-of select="//published[@type='print']/volumeref/link"/>
                  <xsl:text> (</xsl:text>
                  <xsl:choose>
                    <xsl:when test="//published[@type='print']/pubfront/date/year">
                      <xsl:value-of select="//published[@type='print']/pubfront/date/year"/>
                    </xsl:when>
                    <xsl:otherwise>
                      <xsl:value-of select="//published[@type='web']/pubfront/date/year"/>
                    </xsl:otherwise>
                  </xsl:choose>
                  <xsl:text>), </xsl:text>
                  <xsl:value-of select="//published[@type='print']/pubfront/fpage"/>
                    <xsl:if test="string-length(//published[@type='print']/pubfront/lpage/text())!=0">
                    <xsl:text> - </xsl:text>
                    <xsl:value-of select="//published[@type='print']/pubfront/lpage"/>
                  </xsl:if>
                </epdcx:valueString>
              </epdcx:statement>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/elements/1.1/language</xsl:attribute>
                <xsl:attribute name="epdcx:vesURI">http://purl.org/dc/terms/ISO639-2</xsl:attribute>
                <epdcx:valueString>
                  <xsl:value-of select="$langOut"/>
                </epdcx:valueString>
              </epdcx:statement>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/elements/1.1/type</xsl:attribute>
                <xsl:attribute name="epdcx:vesURI">http://purl.org/eprint/terms/Type</xsl:attribute>
                <xsl:attribute name="epdcx:valueURI">http://purl.org/eprint/type/JournalArticle</xsl:attribute>
              </epdcx:statement>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/terms/available</xsl:attribute>
                <epdcx:valueString>
                  <xsl:attribute name="epdcx:sesURI">http://purl.org/dc/terms/W3CDTF</xsl:attribute>
                  <xsl:choose>
                    <xsl:when test="//published[@type='web']/pubfront/date/year">
                      <xsl:call-template name="compose-date">
                        <xsl:with-param name="xpub" select="'web'"/>
                      </xsl:call-template>
                    </xsl:when>
                    <xsl:when test="//published[@type='print']/pubfront/date/year">
                      <xsl:call-template name="compose-date">
                        <xsl:with-param name="xpub" select="'print'"/>
                      </xsl:call-template>
                    </xsl:when>
                    <xsl:otherwise>
                      <xsl:text>1111-11-11</xsl:text>
                    </xsl:otherwise>
                  </xsl:choose>
                </epdcx:valueString>
              </epdcx:statement>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/terms/source</xsl:attribute>
                <epdcx:valueString>
                  <xsl:value-of select="//published[@type='print']/journalref/title"/>
                </epdcx:valueString>
              </epdcx:statement>
              <xsl:for-each select="//published[@type='print']/journalref/issn[@type='print']">
                <epdcx:statement>
                  <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/terms/source</xsl:attribute>
                  <epdcx:valueString>
                    <xsl:text>pISSN:</xsl:text>
                    <xsl:value-of select="normalize-space(text())"/>
                  </epdcx:valueString>
                </epdcx:statement>
              </xsl:for-each>
              <xsl:if test="//published[@type='print']/journalref/issn[@type='online']">
                <xsl:for-each select="//published[@type='print']/journalref/issn[@type='online']">
                  <epdcx:statement>
                    <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/terms/source</xsl:attribute>
                    <epdcx:valueString>
                      <xsl:text>eISSN:</xsl:text>
                      <xsl:value-of select="normalize-space(text())"/>
                    </epdcx:valueString>
                  </epdcx:statement>
                </xsl:for-each>
              </xsl:if>
              <xsl:if test="//published[@type='print']/journalref/coden">
                <xsl:for-each select="//published[@type='print']/journalref/coden">
                  <epdcx:statement>
                    <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/terms/source</xsl:attribute>
                    <epdcx:valueString>
                      <xsl:text>CODEN:</xsl:text>
                      <xsl:value-of select="normalize-space(text())"/>
                    </epdcx:valueString>
                  </epdcx:statement>
                </xsl:for-each>
              </xsl:if>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/terms/publisher</xsl:attribute>
                <epdcx:valueString>
                  <xsl:value-of select="//published[@type='print']/journalref/publisher/orgname/nameelt"/>
                </epdcx:valueString>
              </epdcx:statement>
            </epdcx:description>
            <!-- End of DescriptionSet -->
          </epdcx:descriptionSet>
        </xmlData>
      </mdWrap>
    </dmdSec>
    <!--
    <fileSec>
       <fileGrp ID="sword-mets-fgrp-0" USE="CONTENT">
          <file GROUPID="sword-mets-fgid-1" 
                ID="sword-mets-file-1"
                MIMETYPE="application/pdf" 
                CHECKSUM="2362eff352a3b452523" 
                CHECKSUMTYPE="MD5">
                <FLocat LOCTYPE="URL" xlink:href="pdf1.pdf" />
          </file>
          <file GROUPID="sword-mets-fgid-2" 
                ID="sword-mets-file-2"
                MIMETYPE="application/pdf">
                <FLocat LOCTYPE="URL" xlink:href="pdf2.pdf" />
          </file>
          <file GROUPID="sword-mets-fgid-3" 
                ID="sword-mets-file-3"
                MIMETYPE="application/pdf">
                <FLocat LOCTYPE="URL" xlink:href="pdf3.pdf" />
          </file>
       </fileGrp>
    </fileSec>
    <structMap ID="sword-mets-struct-1" LABEL="structure" TYPE="LOGICAL">
       <div ID="sword-mets-div-0" DMDID="sword-mets-dmd-1" TYPE="SWORD Object">
          <div ID="sword-mets-div-1" TYPE="File">
              <fptr FILEID="sword-mets-file-1" />
          </div>
          <div ID="sword-mets-div-2" TYPE="File">
              <fptr FILEID="sword-mets-file-2" />
          </div>
          <div ID="sword-mets-div-3" TYPE="File">
              <fptr FILEID="sword-mets-file-3" />
          </div>
       </div>
    </structMap>
    -->
  </mets>
  </xsl:template>

  <xsl:template name="compose-date">
    <xsl:param name="xpub" select="'web'"/>
    <xsl:for-each select="//published[@type=$xpub]/pubfront/date">
      <xsl:if test="position() = last()">
        <xsl:variable name="mnth" select="month"/>
        <xsl:value-of select="year"/>
        <xsl:text>-</xsl:text>
        <xsl:choose>
          <xsl:when test="format-number(month,'00')!='NaN'">
            <xsl:value-of select="format-number(month,'00')"/>
          </xsl:when>
          <xsl:when test="document('')//monthNameMap/monthNames[@text=$mnth]/@number">
            <xsl:value-of select="document('')//monthNameMap/monthNames[@text=$mnth]/@number"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:text>12</xsl:text>
          </xsl:otherwise>
        </xsl:choose>
        <xsl:if test="format-number(day,'00')!='NaN'">
          <xsl:text>-</xsl:text>
          <xsl:value-of select="format-number(day,'00')"/>
        </xsl:if>
      </xsl:if>
    </xsl:for-each>
  </xsl:template>

</xsl:stylesheet>
  '''.format(xmlinject1=iso639codes,xmlinject2=mnth2number)


  # 2017-07-12 TD : static string containing the xsl code for JATS --> METSMODS
  #                 Note that there MUST NOT be any kind of '<?xml ...?>' header!
  #
  rsc2metsmods = '''
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

    <!-- <xsl:import href="jats2mods.xsl"/> -->
    <xsl:output method="xml" omit-xml-declaration="no" standalone="no" indent="yes" encoding="utf-8"/>

    <xsl:variable name="inject2">
      {xmlinject2}
    </xsl:variable>

    <xsl:param name="currdatetime">1970-01-01T00:00:00</xsl:param>

    <xsl:template match="/">
        <mets:mets xmlns:mets="http://www.loc.gov/METS/"
                   xmlns:mods="http://www.loc.gov/mods/v3"
              xmlns:xlink="http://www.w3.org/1999/xlink"
              xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
              xsi:schemaLocation="http://www.loc.gov/METS/ http://www.loc.gov/mets/mets.xsd http://www.loc.gov/mods/v3 https://www.loc.gov/standards/mods/v3/mods.xsd">
            <xsl:attribute name="ID"><xsl:text>sword-mets_mets</xsl:text></xsl:attribute>
            <xsl:attribute name="OBJID"><xsl:text>sword-mets</xsl:text></xsl:attribute>
            <xsl:attribute name="LABEL"><xsl:text>METS/MODS SWORD Item</xsl:text></xsl:attribute>
            <xsl:attribute name="PROFILE"><xsl:text>METS/MODS SIP Profile 1.0</xsl:text></xsl:attribute>
            <mets:metsHdr>
                <xsl:attribute name="CREATEDATE"><xsl:value-of select="$currdatetime"/></xsl:attribute>
                <mets:agent>
                    <xsl:attribute name="ROLE">CUSTODIAN</xsl:attribute>
                    <xsl:attribute name="TYPE">ORGANIZATION</xsl:attribute>
                    <mets:name>DeepGreen</mets:name>
                </mets:agent>
            </mets:metsHdr>
            <mets:dmdSec>
                <xsl:attribute name="ID">sword-mets-dmd-1</xsl:attribute>
                <xsl:attribute name="GROUPID">sword-mets-dmd-1_group-1</xsl:attribute>
                <mets:mdWrap>
                    <xsl:attribute name="LABEL"><xsl:text>SWAP Metadata</xsl:text></xsl:attribute>
                    <xsl:attribute name="MDTYPE">MODS</xsl:attribute>
                    <xsl:attribute name="MIMETYPE"><xsl:text>text/xml</xsl:text></xsl:attribute>
                    <mets:xmlData>
                        <xsl:apply-templates/>
                    </mets:xmlData>
                </mets:mdWrap>
            </mets:dmdSec>
        </mets:mets>
    </xsl:template>

    <xsl:template match="/article">
        <mods:mods xmlns:mods="http://www.loc.gov/mods/v3"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                   xsi:schemaLocation="http://www.loc.gov/mods/v3 https://www.loc.gov/standards/mods/v3/mods-3-6.xsd">

            <!--
                Since we are mapping RSC, we are only dealing with journal articles.
                According to a LOC example, these are attributed as follows.
                See https://www.loc.gov/standards/mods/v3/mods-userguide-examples.html#journal_article
            -->
            <mods:typeOfResource>text</mods:typeOfResource>
            <mods:genre>journal article</mods:genre>

            <!-- Language -->
            <mods:language>
                <mods:languageTerm type="code" authority="rfc3066">
                    <xsl:choose>
                        <xsl:when test="//article/@xml:lang">
                            <xsl:value-of select="//article/@xml:lang"/>
                        </xsl:when>
                        <xsl:otherwise>
                            <xsl:text>en</xsl:text>
                        </xsl:otherwise>
                    </xsl:choose>
                </mods:languageTerm>
            </mods:language>

            <!-- Title -->
            <mods:titleInfo>
                <xsl:for-each select="//art-front/titlegrp/title">
                    <mods:title>
                        <xsl:call-template name="insert-lang-attribute"/>
                        <xsl:value-of select="."/>
                    </mods:title>
                </xsl:for-each>
                <xsl:for-each select="//art-front/titlegrp/subtitle">
                    <mods:subTitle>
                        <xsl:call-template name="insert-lang-attribute"/>
                        <xsl:value-of select="."/>
                    </mods:subTitle>
                </xsl:for-each>
            </mods:titleInfo>
            <!-- Seems not to be provided by RSC
            <xsl:for-each select="//art-front/titlegrp/trans-titlegrp/trans-title">
                <mods:titleInfo type="translated">
                    <mods:title>
                        <xsl:call-template name="insert-lang-attribute"/>
                        <xsl:value-of select="."/>
                    </mods:title>
                </mods:titleInfo>
            </xsl:for-each>
            <xsl:for-each select="//art-front/titlegrp/trans-titlegrp/trans-subtitle">
                <mods:titleInfo type="translated">
                    <mods:subTitle>
                        <xsl:call-template name="insert-lang-attribute"/>
                        <xsl:value-of select="."/>
                    </mods:subTitle>
                </mods:titleInfo>
            </xsl:for-each>
            -->

            <!-- Appearance -->
            <mods:relatedItem type="host">
                <mods:titleInfo>
                    <xsl:for-each select="//published[@type='print']/journalref/title[@type='full']">
                        <mods:title>
                            <xsl:call-template name="insert-lang-attribute"/>
                            <xsl:value-of select="."/>
                        </mods:title>
                    </xsl:for-each>
                </mods:titleInfo>
                <xsl:if test="//published[@type='print']/journalref/issn[@type='print']">
                    <mods:identifier type="issn"><xsl:value-of select="//published[@type='print']/journalref/issn[@type='print']"/></mods:identifier>
                </xsl:if>
                <xsl:if test="//published[@type='print']/journalref/issn[@type='online']">
                    <mods:identifier type="eIssn"><xsl:value-of select="//published[@type='print']/journalref/issn[@type='online']"/></mods:identifier>
                </xsl:if>
                <xsl:if test="//published[@type='print']/journalref/title[@type='abbreviated']">
                    <mods:identifier type="abbreviated">
                       <xsl:value-of select="//published[@type='print']/journalref/title[@type='abbreviated']"/>
                    </mods:identifier>
                </xsl:if>
                <xsl:for-each select="//published[@type='print']/journalref/sercode">
                    <mods:identifier type="sercode"><xsl:value-of select="."/></mods:identifier>
                </xsl:for-each>
                <xsl:for-each select="//published[@type='print']/journalref/coden">
                    <mods:identifier type="coden"><xsl:value-of select="."/></mods:identifier>
                </xsl:for-each>
                <mods:part>
                    <xsl:if test="string-length(//published[@type='print']/volumeref/link/text()) > 0">
                        <mods:detail type="volume">
                            <mods:number><xsl:value-of select="//published[@type='print']/volumeref/link"/></mods:number>
                        </mods:detail>
                    </xsl:if>
                    <xsl:if test="string-length(//published[@type='print']/issueref/link/text()) > 0">
                        <mods:detail type="issue">
                            <mods:number><xsl:value-of select="//published[@type='print']/issueref/link"/></mods:number>
                        </mods:detail>
                    </xsl:if>
                    <xsl:if test="string-length(//published[@type='print']/pubfront/fpage/text()) > 0">
                        <mods:extent unit="pages">
                            <mods:start><xsl:value-of select="//published[@type='print']/pubfront/fpage"/></mods:start>
                            <xsl:if test="string-length(//published[@type='print']/pubfront/lpage/text()) > 0">
                                <mods:end><xsl:value-of select="//published[@type='print']/pubfront/lpage"/></mods:end>
                            </xsl:if>
                        </mods:extent>
                    </xsl:if>
                </mods:part>
            </mods:relatedItem>

            <!-- Creator / Contributor (Author, Editor...)-->
            <xsl:for-each select="//art-front/authgrp/author">
                <mods:name type="personal">
                    <mods:namePart type="family"><xsl:copy-of select="person/persname/surname/text()"/></mods:namePart>
                    <xsl:if test="string-length(person/persname/fname/text()) > 0">
                        <mods:namePart type="given"><xsl:copy-of select="person/persname/fname/text()"/></mods:namePart>
                    </xsl:if>
                    <mods:role>
                        <mods:roleTerm type="text"><xsl:text>author</xsl:text></mods:roleTerm>
                    </mods:role>
                    <!-- Affiliation -->
                    <xsl:if test="string-length(./@aff) > 0">
                        <xsl:variable name="affs" select="@aff"/>
                        <xsl:for-each select="//art-front/authgrp/aff[contains($affs,@id)]">
                            <mods:affiliation>
                                <xsl:for-each select="org/orgname/nameelt">
                                    <xsl:value-of select="normalize-space(text())"/>
                                    <xsl:if test="position() != last()">
                                        <xsl:text>, </xsl:text>
                                    </xsl:if>
                                 </xsl:for-each>
                            </mods:affiliation>
                        </xsl:for-each>
                    </xsl:if>
                </mods:name>
            </xsl:for-each>

            <!-- Description: Abstract / TOC -->
            <xsl:for-each select="//art-front/abstract">
                <!-- TOC is not available within RSC
                    <xsl:when test="@type = 'toc'">
                        <mods:tableOfContents>
                            <xsl:call-template name="insert-lang-attribute"/>
                            <xsl:value-of select="."/>
                        </mods:tableOfContents>
                    </xsl:when>
                -->
                <mods:abstract>
                    <xsl:call-template name="insert-lang-attribute"/>
                    <xsl:value-of select="."/>
                </mods:abstract>
            </xsl:for-each>

            <!-- Description: Subject (Keywords) -->
            <!-- Keywords are not provided by RSC
            <xsl:if test="//article-meta/kwd-group/kwd">
                <mods:subject>
                    <xsl:for-each select="//article-meta/kwd-group/kwd">
                        <mods:topic><xsl:value-of select="."/></mods:topic>
                    </xsl:for-each>
                </mods:subject>
            </xsl:if>
            -->

            <!-- Publisher, Dates (in MODS under originInfo) -->
            <mods:originInfo>
                <mods:publisher>
                    <xsl:for-each select="//published[@type='print']/journalref/publisher/orgname/nameelt">
                        <xsl:value-of select="normalize-space(text())"/>
                        <xsl:if test="position() != last()">
                            <xsl:text>, </xsl:text>
                        </xsl:if>
                    </xsl:for-each>
                </mods:publisher>
                <!-- Place of publishing is not provided by RSC
                <mods:place>
                    <mods:placeTerm type="text"><xsl:value-of select="//journal-meta/publisher/publisher-loc"/></mods:placeTerm>
                </mods:place>
                -->

                <!-- Publication date (= date available/issued) -->
                <xsl:for-each select="//published[@type='web']/pubfront/date">
                    <xsl:if test="year and month">
                        <mods:dateIssued encoding="iso8601">
                            <xsl:call-template name="compose-date"></xsl:call-template>
                        </mods:dateIssued>
                    </xsl:if>
                </xsl:for-each>

                <!-- Other dates (received, accepted...) -->
                <xsl:for-each select="//art-admin/received/date">
                    <xsl:if test="year and month">
                        <mods:dateOther encoding="iso8601" type="received">
                            <xsl:call-template name="compose-date"></xsl:call-template>
                        </mods:dateOther>
                    </xsl:if>
                </xsl:for-each>
                <xsl:for-each select="//art-admin/date">
                    <xsl:if test="year and month">
                        <mods:dateOther encoding="iso8601">
                            <xsl:attribute name="type"><xsl:value-of select="@role"/></xsl:attribute>
                            <xsl:call-template name="compose-date"></xsl:call-template>
                        </mods:dateOther>
                    </xsl:if>
                </xsl:for-each>
            </mods:originInfo>

            <!-- Identifiers -->
            <xsl:for-each select="//art-admin/doi">
                <mods:identifier type="doi">
                    <xsl:value-of select="."/>
                </mods:identifier>
            </xsl:for-each>
            <xsl:for-each select="//art-admin/ms-id">
                <mods:identifier type="ms-id">
                    <xsl:value-of select="."/>
                </mods:identifier>
            </xsl:for-each>

            <!-- License / Copyright -->
            <xsl:for-each select="//published[@type='web']/journalref/cpyrt">
                <mods:accessCondition type="use and reproduction">
                    <xsl:value-of select="."/>
                </mods:accessCondition>
            </xsl:for-each>

            <!-- Funding -->
            <!-- Funding source is not included by RSC
            <xsl:for-each select="//article-meta/funding-group/award-group/funding-source">
                <mods:note type="funding">
                    <xsl:value-of select="."/>
                </mods:note>
            </xsl:for-each>
            -->

        </mods:mods>

    </xsl:template>

    <xsl:template name="compose-date">
        <xsl:variable name="mnth" select="month"/>
        <xsl:value-of select="year"/>
        <xsl:text>-</xsl:text>
        <xsl:choose>
            <xsl:when test="format-number(month,'00')!='NaN'">
                <xsl:value-of select="format-number(month,'00')"/>
            </xsl:when>
            <xsl:when test="document('')//monthNameMap/monthNames[@text=$mnth]/@number">
                <xsl:value-of select="document('')//monthNameMap/monthNames[@text=$mnth]/@number"/>
            </xsl:when>
            <xsl:otherwise>
                <xsl:text>12</xsl:text>
            </xsl:otherwise>
        </xsl:choose>
        <xsl:if test="format-number(day,'00')!='NaN'">
            <xsl:text>-</xsl:text>
            <xsl:value-of select="format-number(day,'00')"/>
        </xsl:if>
    </xsl:template>

    <xsl:template name="insert-lang-attribute">
        <xsl:if test="@xml:lang">
            <xsl:attribute name="xml:lang"><xsl:value-of select="@xml:lang"/></xsl:attribute>
        </xsl:if>
    </xsl:template>

</xsl:stylesheet>
  '''.format(xmlinject2=mnth2number)


  # -----------------------------------------------------------------------------
  # =============================================================================
  # -----------------------------------------------------------------------------


  # 2017-05-15 TD : static string containing the xsl code for JATS --> ESciDoc
  #                 Note that there MUST NOT be any kind of '<?xml ...?>' header!
  #
  # 2019-09-24 TD : Eliminate the tag 'journal-title-group' in xpath since a publisher 
  #                 (i.e. Frontiers) apparently is not using it
  #
  jats2escidoc = '''
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

  <xsl:output method="xml" indent="yes" encoding="UTF-8"/>

  <xsl:param name="contentmodel"><xsl:text>escidoc:persistent4</xsl:text></xsl:param>

  <xsl:variable name="inject">
    {xmlinject}
  </xsl:variable>
  <xsl:variable name="langIn" select="translate(/article/@xml:lang,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"/>
  <xsl:variable name="langOut" select="document('')//langCodeMap/langCodes[@iso639-1=$langIn]/@iso639-3"/>

  <xsl:key name="kAffById" match="//article-meta/aff" use="@id"/>

  <xsl:template match="/">
  <escidocItem:item xmlns:escidocContext="http://www.escidoc.de/schemas/context/0.7"
    xmlns:escidocContextList="http://www.escidoc.de/schemas/contextlist/0.7"
    xmlns:escidocComponents="http://www.escidoc.de/schemas/components/0.9"
    xmlns:escidocItem="http://www.escidoc.de/schemas/item/0.10"
    xmlns:escidocItemList="http://www.escidoc.de/schemas/itemlist/0.10"
    xmlns:escidocMetadataRecords="http://www.escidoc.de/schemas/metadatarecords/0.5"
    xmlns:escidocRelations="http://www.escidoc.de/schemas/relations/0.3"
    xmlns:escidocSearchResult="http://www.escidoc.de/schemas/searchresult/0.8"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:prop="http://escidoc.de/core/01/properties/"
    xmlns:srel="http://escidoc.de/core/01/structural-relations/"
    xmlns:version="http://escidoc.de/core/01/properties/version/"
    xmlns:release="http://escidoc.de/core/01/properties/release/"
    xmlns:member-list="http://www.escidoc.de/schemas/memberlist/0.10"
    xmlns:container="http://www.escidoc.de/schemas/container/0.9"
    xmlns:container-list="http://www.escidoc.de/schemas/containerlist/0.9"
    xmlns:struct-map="http://www.escidoc.de/schemas/structmap/0.4"
    xmlns:mods-md="http://www.loc.gov/mods/v3"
    xmlns:file="http://purl.org/escidoc/metadata/profiles/0.1/file"
    xmlns:publication="http://purl.org/escidoc/metadata/profiles/0.1/publication"
    xmlns:yearbook="http://purl.org/escidoc/metadata/profiles/0.1/yearbook"
    xmlns:face="http://purl.org/escidoc/metadata/profiles/0.1/face"
    xmlns:jhove="http://hul.harvard.edu/ois/xml/ns/jhove">
      <escidocItem:properties>
        <srel:content-model>
          <xsl:attribute name="objid"><xsl:value-of select="$contentmodel"/></xsl:attribute>
        </srel:content-model>
        <prop:content-model-specific xmlns:prop="http://escidoc.de/core/01/properties/"/> 
      </escidocItem:properties>
      <escidocMetadataRecords:md-records>
        <escidocMetadataRecords:md-record>
          <xsl:attribute name="name"><xsl:text>escidoc</xsl:text></xsl:attribute>
          <publication:publication xmlns:dc="http://purl.org/dc/elements/1.1/"
            xmlns:dcterms="http://purl.org/dc/terms/"
            xmlns:eterms="http://purl.org/escidoc/metadata/terms/0.1/"
            xmlns:person="http://purl.org/escidoc/metadata/profiles/0.1/person" 
            xmlns:event="http://purl.org/escidoc/metadata/profiles/0.1/event" 
            xmlns:source="http://purl.org/escidoc/metadata/profiles/0.1/source" 
            xmlns:organization="http://purl.org/escidoc/metadata/profiles/0.1/organization" 
            xmlns:legalCase="http://purl.org/escidoc/metadata/profiles/0.1/legal-case"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <xsl:attribute name="type"><xsl:text>http://purl.org/escidoc/metadata/ves/publication-types/article</xsl:text></xsl:attribute>
            <xsl:for-each select="//article-meta/contrib-group/contrib">
              <eterms:creator>
                <xsl:attribute name="role">
                  <xsl:text>http://www.loc.gov/loc.terms/relators/</xsl:text>
                  <xsl:choose>
                    <xsl:when test="contains(@contrib-type,'editor')"><xsl:text>EDT</xsl:text></xsl:when>
                    <xsl:otherwise><xsl:text>AUT</xsl:text></xsl:otherwise>
                  </xsl:choose>
                </xsl:attribute>
                <person:person>
                  <eterms:family-name><xsl:copy-of select="name/surname/text()"/></eterms:family-name>
                  <eterms:given-name><xsl:copy-of select="name/given-names/text()"/></eterms:given-name>
                      <xsl:choose>
                        <xsl:when test="contains(xref/@ref-type,'aff') and string-length(xref/@rid)!=0">
                           <xsl:for-each select="./xref[@ref-type='aff']">
                             <organization:organization>
                               <dc:title><xsl:copy-of select="key('kAffById', @rid)/text()"/></dc:title>
                               <!-- <eterms:address><xsl:copy-of select="key('kAffById', @rid)/text()"/></eterms:address> -->
                               <!--
                               <dc:title><xsl:value-of select="key('kAffById', @rid)/text()[normalize-space()][1]"/></dc:title>
                               -->
                               <!-- for an explanation of the last select expression see 
                                    http://stackoverflow.com/questions/16134646/how-to-return-text-of-node-without-child-nodes-text
                                    the solved problem here is to get rid of the footnote markers inside the affiliation texts that are often given by child nodes...
                                -->
                             </organization:organization>
                          </xsl:for-each> 
                        </xsl:when>
                        <xsl:when test="not(contains(xref/@ref-type,'aff')) and string-length(//article-meta/aff[position()=last()]/text())!=0">
                          <xsl:for-each select="//article-meta/aff[not(@*)]">
                            <organization:organization>
                              <dc:title><xsl:copy-of select="./text()"/></dc:title>
                              <!-- <eterms:address><xsl:copy-of select="./text()"/></eterms:address> -->
                            </organization:organization>
                          </xsl:for-each>
                        </xsl:when>
                        <xsl:otherwise>
                           <organization:organization>
                             <dc:title><xsl:text>-</xsl:text></dc:title> 
                             <!-- <eterms:address><xsl:text>-</xsl:text></eterms:address> -->
                           </organization:organization>
                        </xsl:otherwise>
                      </xsl:choose>
                  <!--
                  <organization:organization>
                    <dc:title></dc:title>
                    <eterms:address/>
                  </organization:organization>
                  -->
                </person:person>
              </eterms:creator>
            </xsl:for-each>
            <dc:title><xsl:value-of select="//article-meta/title-group/article-title"/></dc:title>
            <dc:language>
              <xsl:attribute name="xsi:type"><xsl:text>dcterms:ISO639-3</xsl:text></xsl:attribute>
              <xsl:value-of select="$langOut"/>
            </dc:language>
            <dc:identifier>
              <xsl:attribute name="xsi:type"><xsl:text>eterms:DOI</xsl:text></xsl:attribute>
              <xsl:value-of select="//article-meta/article-id[@pub-id-type='doi']"/>
            </dc:identifier>
            <xsl:if test="//article-meta/article-id[@pub-id-type='pmid']">
              <dc:identifier>
                <xsl:attribute name="xsi:type"><xsl:text>eterms:PMID</xsl:text></xsl:attribute>
                <xsl:value-of select="//article-meta/article-id[@pub-id-type='pmid']"/>
              </dc:identifier>
            </xsl:if>
            <dcterms:issued>
              <xsl:attribute name="xsi:type"><xsl:text>dcterms:W3CDTF</xsl:text></xsl:attribute>
              <xsl:choose>
                <xsl:when test="//article-meta/pub-date[contains(@pub-type,'epub')]/year">
                  <xsl:call-template name="compose-date">
                    <xsl:with-param name="xpub" select="'epub'"/>
                  </xsl:call-template>
                </xsl:when>
                <xsl:when test="//article-meta/pub-date[contains(@pub-type,'ppub')]/year">
                  <xsl:call-template name="compose-date">
                    <xsl:with-param name="xpub" select="'ppub'"/>
                  </xsl:call-template>
                </xsl:when>
                <xsl:when test="//article-meta/pub-date[contains(@date-type,'pub')]/year">
                  <xsl:call-template name="compose-date">
                    <xsl:with-param name="xpub" select="'pub'"/>
                    <!-- <xsl:with-param name="xtype" select="@date-type"/> -->
                  </xsl:call-template>
                </xsl:when>
                <xsl:otherwise>
                  <xsl:text>1111-11-11</xsl:text>
                </xsl:otherwise>
              </xsl:choose>
            </dcterms:issued>
            <source:source>
              <xsl:attribute name="type"><xsl:text>http://purl.org/escidoc/metadata/ves/publication-types/journal</xsl:text></xsl:attribute>
              <dc:title><xsl:value-of select="//journal-meta//journal-title"/></dc:title>
              <eterms:volume><xsl:value-of select="//article-meta/volume"/></eterms:volume>
              <eterms:issue><xsl:value-of select="//article-meta/issue"/></eterms:issue>
              <eterms:start-page><xsl:value-of select="//article-meta/fpage"/></eterms:start-page>
              <eterms:end-page><xsl:value-of select="//article-meta/lpage"/></eterms:end-page>
              <xsl:if test="string-length(//article-meta/fpage/text())!=0 and string-length(//article-meta/lpage/text())!=0">
                <eterms:total-number-of-pages><xsl:value-of select="//article-meta/lpage - //article-meta/fpage + 1"/></eterms:total-number-of-pages>
              </xsl:if>
              <eterms:publishing-info>
                <dc:publisher><xsl:value-of select="//journal-meta/publisher/publisher-name"/></dc:publisher>
                <eterms:place><xsl:value-of select="//journal-meta/publisher/publisher-loc"/></eterms:place>
              </eterms:publishing-info>
              <xsl:if test="//journal-meta/issn[@pub-type='ppub']">
                <dc:identifier>
                  <xsl:attribute name="xsi:type"><xsl:text>eterms:ISSN</xsl:text></xsl:attribute>
                  <xsl:value-of select="//journal-meta/issn[@pub-type='ppub']"/><xsl:text> (pISSN)</xsl:text>
                </dc:identifier>
              </xsl:if>
              <xsl:if test="//journal-meta/issn[@pub-type='epub']">
                <dc:identifier>
                  <xsl:attribute name="xsi:type"><xsl:text>eterms:ISSN</xsl:text></xsl:attribute>
                  <xsl:value-of select="//journal-meta/issn[@pub-type='epub']"/><xsl:text> (eISSN)</xsl:text>
                </dc:identifier>
              </xsl:if>
              <xsl:if test="//journal-meta/issn[@publication-format='print']">
                <dc:identifier>
                  <xsl:attribute name="xsi:type"><xsl:text>eterms:ISSN</xsl:text></xsl:attribute>
                  <xsl:value-of select="//journal-meta/issn[@publication-format='print']"/><xsl:text> (pISSN)</xsl:text>
                </dc:identifier>
              </xsl:if>
              <xsl:if test="//journal-meta/issn[@publication-format='electronic']">
                <dc:identifier>
                  <xsl:attribute name="xsi:type"><xsl:text>eterms:ISSN</xsl:text></xsl:attribute>
                  <xsl:value-of select="//journal-meta/issn[@publication-format='electronic']"/><xsl:text> (eISSN)</xsl:text>
                </dc:identifier>
              </xsl:if>
            </source:source>
            <dcterms:abstract><xsl:value-of select="//article-meta/abstract"/></dcterms:abstract>
            <dcterms:subject>
              <xsl:for-each select="//article-meta/kwd-group/kwd">
                <xsl:value-of select="normalize-space(text())"/>
                <xsl:if test="position() != last()">
                  <xsl:text> , </xsl:text>
                </xsl:if>
              </xsl:for-each>
            </dcterms:subject>
            <dc:subject>
              <xsl:attribute name="xsi:type"><xsl:text>eterms:DDC</xsl:text></xsl:attribute>
            </dc:subject>
          </publication:publication>
        </escidocMetadataRecords:md-record>
      </escidocMetadataRecords:md-records>
    </escidocItem:item>
  </xsl:template>

  <xsl:template name="compose-date">
    <xsl:param name="xpub" select="'epub'"/>
    <xsl:value-of select="//article-meta/pub-date[contains(@pub-type,$xpub)]/year"/>
    <xsl:text>-</xsl:text>
    <xsl:choose>
      <xsl:when test="//article-meta/pub-date[contains(@pub-type,$xpub)]/month">
        <xsl:value-of select="format-number(//article-meta/pub-date[contains(@pub-type,$xpub)]/month,'00')"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:text>12</xsl:text>
      </xsl:otherwise>
      </xsl:choose>
      <xsl:if test="//article-meta/pub-date[contains(@pub-type,$xpub)]/day">
        <xsl:text>-</xsl:text>
        <xsl:value-of select="format-number(//article-meta/pub-date[contains(@pub-type,$xpub)]/day,'00')"/>
      </xsl:if>
  </xsl:template>

</xsl:stylesheet>
  '''.format(xmlinject=iso639codes)


  # 2017-05-15 TD : static string containing the xsl code for JATS --> METSDspaceSIP
  #                 Note that there MUST NOT be any kind of '<?xml ...?>' header!
  #
  # 2019-09-24 TD : Eliminate the tag 'journal-title-group' in xpath since a publisher 
  #                 (i.e. Frontiers) apparently is not using it
  #
  jats2metsdspace = '''
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

  <!-- <xsl:import href="outputTokens.xsl"/> -->
  <xsl:output method="xml" omit-xml-declaration="no" standalone="no" indent="yes" encoding="utf-8"/>

  <xsl:param name="currdatetime">1970-01-01T00:00:00</xsl:param>

  <xsl:variable name="inject">
    {xmlinject}
  </xsl:variable>
  <xsl:variable name="langIn" select="translate(/article/@xml:lang,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"/>
  <!-- <xsl:variable name="langOut">eng</xsl:variable> -->
  <xsl:variable name="langOut" select="document('')//langCodeMap/langCodes[@iso639-1=$langIn]/@iso639-2"/>

  <xsl:template match="/">
  <mets xmlns="http://www.loc.gov/METS/"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.loc.gov/METS/ http://www.loc.gov/standards/mets/mets.xsd">
    <xsl:attribute name="ID"><xsl:text>sword-mets_mets</xsl:text></xsl:attribute>
    <xsl:attribute name="OBJID"><xsl:text>sword-mets</xsl:text></xsl:attribute>
    <xsl:attribute name="LABEL"><xsl:text>DSpace SWORD Item</xsl:text></xsl:attribute>
    <xsl:attribute name="PROFILE"><xsl:text>DSpace METS SIP Profile 1.0</xsl:text></xsl:attribute>
    <metsHdr>
      <xsl:attribute name="CREATEDATE"><xsl:value-of select="$currdatetime"/></xsl:attribute>
      <agent>
        <xsl:attribute name="ROLE">CUSTODIAN</xsl:attribute>
        <xsl:attribute name="TYPE">ORGANIZATION</xsl:attribute>
        <name>Green DeepGreen</name>
      </agent>
    </metsHdr>
    <dmdSec>
      <xsl:attribute name="ID">sword-mets-dmd-1</xsl:attribute>
      <xsl:attribute name="GROUPID">sword-mets-dmd-1_group-1</xsl:attribute>
      <mdWrap>
        <xsl:attribute name="LABEL"><xsl:text>SWAP Metadata</xsl:text></xsl:attribute>
        <xsl:attribute name="MDTYPE">OTHER</xsl:attribute>
        <xsl:attribute name="OTHERMDTYPE">EPDCX</xsl:attribute>
        <xsl:attribute name="MIMETYPE"><xsl:text>text/xml</xsl:text></xsl:attribute>
        <xmlData>
          <epdcx:descriptionSet xmlns:epdcx="http://purl.org/eprint/epdcx/2006-11-16/"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://purl.org/eprint/epdcx/2006-11-16/ http://purl.org/eprint/epdcx/xsd/2006-11-16/epdcx.xsd">
            <epdcx:description>
              <xsl:attribute name="epdcx:resourceId">sword-mets-epdcx-1</xsl:attribute>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/elements/1.1/type</xsl:attribute>
                <xsl:attribute name="epdcx:valueURI">http://purl.org/eprint/entityType/ScholarlyWork</xsl:attribute>
              </epdcx:statement>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/elements/1.1/title</xsl:attribute>
                <epdcx:valueString><xsl:value-of select="//article-meta/title-group/article-title"/></epdcx:valueString>
              </epdcx:statement>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/terms/abstract</xsl:attribute>
                <epdcx:valueString><xsl:value-of select="//article-meta/abstract"/></epdcx:valueString>
              </epdcx:statement>
              <xsl:for-each select="//article-meta/contrib-group/contrib">
                <epdcx:statement>
                  <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/elements/1.1/creator</xsl:attribute>
                  <epdcx:valueString>
                    <xsl:value-of select="name/surname"/>
                    <xsl:if test="string-length(name/given-names/text()) > 0">
                      <xsl:text>, </xsl:text>
                      <xsl:value-of select="name/given-names"/>
                    </xsl:if>
                  </epdcx:valueString>
                </epdcx:statement>
              </xsl:for-each>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/elements/1.1/identifier</xsl:attribute>
                <epdcx:valueString>
                  <xsl:attribute name="epdcx:sesURI">http://purl.org/dc/terms/URI</xsl:attribute>
                  <xsl:text>https://dx.doi.org/</xsl:text>
                  <xsl:value-of select="//article-meta/article-id[@pub-id-type='doi']"/>
                </epdcx:valueString>
              </epdcx:statement>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/eprint/terms/isExpressedAs</xsl:attribute>
                <xsl:attribute name="epdcx:valueRef">sword-mets-expr-1</xsl:attribute>
              </epdcx:statement>
            </epdcx:description>
            <!-- Second (level?) description starts here -->
            <epdcx:description>
              <xsl:attribute name="epdcx:resourceId">sword-mets-expr-1</xsl:attribute>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/elements/1.1/type</xsl:attribute>
                <xsl:attribute name="epdcx:valueURI">http://purl.org/eprint/entityType/Expression</xsl:attribute>
              </epdcx:statement>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/terms/bibliographicCitation</xsl:attribute>
                <epdcx:valueString>
                  <xsl:value-of select="//article-meta/contrib-group/contrib[position()=1]/name/surname"/>
                  <xsl:if test="string-length(//article-meta/contrib-group/contrib[position()=1]/name/given-names/text()) > 0">
                    <xsl:text>, </xsl:text>
                    <xsl:value-of select="//article-meta/contrib-group/contrib[position()=1]/name/given-names"/>
                  </xsl:if>
                  <xsl:if test="//article-meta/contrib-group/contrib[position()>1]">
                    <xsl:text> et al.</xsl:text>
                  </xsl:if>
                  <xsl:text>: </xsl:text>
                  <xsl:for-each select="//journal-meta//journal-title">
                    <xsl:value-of select="normalize-space(text())"/>
                    <xsl:text> </xsl:text>
                  </xsl:for-each>
                  <xsl:value-of select="//article-meta/volume"/>
                  <xsl:text> (</xsl:text>
                  <xsl:choose>
                    <xsl:when test="//article-meta/pub-date[contains(@pub-type,'ppub')]/year">
                      <xsl:value-of select="//article-meta/pub-date[contains(@pub-type,'ppub')]/year"/>
                    </xsl:when>
                    <xsl:when test="//article-meta/pub-date[contains(@pub-type,'epub')]/year">
                      <xsl:value-of select="//article-meta/pub-date[contains(@pub-type,'epub')]/year"/>
                    </xsl:when>
                    <xsl:when test="//article-meta/pub-date[contains(@publication-format,'electronic') and contains(@date-type,'pub')]/year">
                      <xsl:value-of select="//article-meta/pub-date[contains(@publication-format,'electronic') and contains(@date-type,'pub')]/year"/>
                    </xsl:when>
                    <xsl:otherwise>
                      <xsl:value-of select="//article-meta/pub-date[contains(@date-type,'pub')]/year"/>
                    </xsl:otherwise>
                  </xsl:choose>
                  <xsl:text>), </xsl:text>
                  <xsl:value-of select="//article-meta/fpage"/>
                    <xsl:if test="string-length(//article-meta/lpage/text())!=0">
                    <xsl:text> - </xsl:text>
                    <xsl:value-of select="//article-meta/lpage"/>
                  </xsl:if>
                </epdcx:valueString>
              </epdcx:statement>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/elements/1.1/language</xsl:attribute>
                <xsl:attribute name="epdcx:vesURI">http://purl.org/dc/terms/ISO639-2</xsl:attribute>
                <epdcx:valueString>
                  <xsl:value-of select="$langOut"/>
                </epdcx:valueString>
              </epdcx:statement>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/elements/1.1/type</xsl:attribute>
                <xsl:attribute name="epdcx:vesURI">http://purl.org/eprint/terms/Type</xsl:attribute>
                <xsl:attribute name="epdcx:valueURI">http://purl.org/eprint/type/JournalArticle</xsl:attribute>
              </epdcx:statement>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/terms/available</xsl:attribute>
                <epdcx:valueString>
                  <xsl:attribute name="epdcx:sesURI">http://purl.org/dc/terms/W3CDTF</xsl:attribute>
                  <xsl:choose>
                    <xsl:when test="//article-meta/pub-date[contains(@pub-type,'epub')]/year">
                      <xsl:call-template name="compose-date">
                        <xsl:with-param name="xpub" select="'epub'"/>
                      </xsl:call-template>
                    </xsl:when>
                    <xsl:when test="//article-meta/pub-date[contains(@pub-type,'ppub')]/year">
                      <xsl:call-template name="compose-date">
                        <xsl:with-param name="xpub" select="'ppub'"/>
                      </xsl:call-template>
                    </xsl:when>
                    <xsl:when test="//article-meta/pub-date[contains(@date-type,'pub')]/year">
                      <xsl:call-template name="compose-date">
                        <xsl:with-param name="xpub" select="'pub'"/>
                        <!-- <xsl:with-param name="xtype" select="@date-type"/> -->
                      </xsl:call-template>
                    </xsl:when>
                    <xsl:otherwise>
                      <xsl:text>1111-11-11</xsl:text>
                    </xsl:otherwise>
                  </xsl:choose>
                </epdcx:valueString>
              </epdcx:statement>
              <xsl:for-each select="//journal-meta//journal-title">
                <epdcx:statement>
                  <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/terms/source</xsl:attribute>
                  <epdcx:valueString>
                    <xsl:value-of select="normalize-space(text())"/>
                  </epdcx:valueString>
                </epdcx:statement>
              </xsl:for-each>
              <xsl:for-each select="//journal-meta/issn[@pub-type='ppub' or @publication-format='print']">
                <epdcx:statement>
                  <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/terms/source</xsl:attribute>
                  <epdcx:valueString>
                    <xsl:text>pISSN:</xsl:text>
                    <xsl:value-of select="normalize-space(text())"/>
                  </epdcx:valueString>
                </epdcx:statement>
              </xsl:for-each>
              <xsl:for-each select="//journal-meta/issn[@pub-type='epub' or @publication-format='electronic']">
                <epdcx:statement>
                  <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/terms/source</xsl:attribute>
                  <epdcx:valueString>
                    <xsl:text>eISSN:</xsl:text>
                    <xsl:value-of select="normalize-space(text())"/>
                  </epdcx:valueString>
                </epdcx:statement>
              </xsl:for-each>
              <epdcx:statement>
                <xsl:attribute name="epdcx:propertyURI">http://purl.org/dc/terms/publisher</xsl:attribute>
                <epdcx:valueString>
                  <xsl:value-of select="//journal-meta/publisher/publisher-name"/>
                </epdcx:valueString>
              </epdcx:statement>
            </epdcx:description>
            <!-- End of DescriptionSet -->
          </epdcx:descriptionSet>
        </xmlData>
      </mdWrap>
    </dmdSec>
    <!--
    <fileSec>
       <fileGrp ID="sword-mets-fgrp-0" USE="CONTENT">
          <file GROUPID="sword-mets-fgid-1" 
                ID="sword-mets-file-1"
                MIMETYPE="application/pdf" 
                CHECKSUM="2362eff352a3b452523" 
                CHECKSUMTYPE="MD5">
                <FLocat LOCTYPE="URL" xlink:href="pdf1.pdf" />
          </file>
          <file GROUPID="sword-mets-fgid-2" 
                ID="sword-mets-file-2"
                MIMETYPE="application/pdf">
                <FLocat LOCTYPE="URL" xlink:href="pdf2.pdf" />
          </file>
          <file GROUPID="sword-mets-fgid-3" 
                ID="sword-mets-file-3"
                MIMETYPE="application/pdf">
                <FLocat LOCTYPE="URL" xlink:href="pdf3.pdf" />
          </file>
       </fileGrp>
    </fileSec>
    <structMap ID="sword-mets-struct-1" LABEL="structure" TYPE="LOGICAL">
       <div ID="sword-mets-div-0" DMDID="sword-mets-dmd-1" TYPE="SWORD Object">
          <div ID="sword-mets-div-1" TYPE="File">
              <fptr FILEID="sword-mets-file-1" />
          </div>
          <div ID="sword-mets-div-2" TYPE="File">
              <fptr FILEID="sword-mets-file-2" />
          </div>
          <div ID="sword-mets-div-3" TYPE="File">
              <fptr FILEID="sword-mets-file-3" />
          </div>
       </div>
    </structMap>
    -->
  </mets>
  </xsl:template>

  <xsl:template name="compose-date">
    <xsl:param name="xpub" select="'epub'"/>
    <xsl:value-of select="//article-meta/pub-date[contains(@pub-type,$xpub)]/year"/>
    <xsl:text>-</xsl:text>
    <xsl:choose>
      <xsl:when test="//article-meta/pub-date[contains(@pub-type,$xpub)]/month">
        <xsl:value-of select="format-number(//article-meta/pub-date[contains($pub-type,$xpub)]/month,'00')"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:text>12</xsl:text>
      </xsl:otherwise>
      </xsl:choose>
      <xsl:if test="//article-meta/pub-date[contains(@pub-type,$xpub)]/day">
        <xsl:text>-</xsl:text>
        <xsl:value-of select="format-number(//article-meta/pub-date[contains(@pub-type,$xpub)]/day,'00')"/>
      </xsl:if>
  </xsl:template>

</xsl:stylesheet>
  '''.format(xmlinject=iso639codes)



  # -----------------------------------------------------------------------------
  # =============================================================================
  # -----------------------------------------------------------------------------


  # 2017-03-30 TD : xslt specific to file addition to already transformed opus4.xml
  #                 Note again that, here too, there MUST NOT be any "<?xml ...>" header!
  #
  # 2019-08-08 TD : fix the overriding 'identity rule' of the copying process
  #                 Only *one* file was added in the version before. Bad, bad, bad...
  #
  addfiles2opus4 = '''
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

  <xsl:output method="xml" omit-xml-declaration="yes" indent="yes" encoding="utf-8"/>

  <xsl:param name="file"/>
  <xsl:param name="md5"/>

  <xsl:template match="@*|node()">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()"/>
    </xsl:copy>
  </xsl:template>

  <xsl:template match="opusDocument">
    <xsl:copy>
      <xsl:apply-templates select="@* | *"/>
      <xsl:if test="not(./files) and string-length($file)!=0 and string-length($md5)!=0">
        <files>
           <xsl:attribute name="basedir"><xsl:text>.</xsl:text></xsl:attribute>
           <file>
             <xsl:attribute name="name"><xsl:value-of select="$file"/></xsl:attribute>
             <xsl:attribute name="language"><xsl:value-of select="//opusDocument/@language"/></xsl:attribute>
             <xsl:attribute name="visibleInOai"><xsl:text>true</xsl:text></xsl:attribute>
             <comment>
               <!-- <xsl:text>A component of the fulltext article</xsl:text> -->
             </comment>
             <checksum>
               <xsl:attribute name="type"><xsl:text>md5</xsl:text></xsl:attribute>
               <xsl:value-of select="$md5"/>
             </checksum>
           </file>
        </files>
      </xsl:if>
    </xsl:copy>
  </xsl:template>
  
  <xsl:template match="files">
    <xsl:copy>
      <xsl:apply-templates select="@* | *"/>
      <xsl:if test="string-length($file)!=0 and string-length($md5)!=0">
        <file>
          <xsl:attribute name="name"><xsl:value-of select="$file"/></xsl:attribute>
          <xsl:attribute name="language"><xsl:value-of select="//opusDocument/@language"/></xsl:attribute>
          <xsl:attribute name="visibleInOai"><xsl:text>true</xsl:text></xsl:attribute>
          <comment>
            <!-- <xsl:text>A component of the fulltext article</xsl:text> -->
          </comment>
          <checksum>
            <xsl:attribute name="type"><xsl:text>md5</xsl:text></xsl:attribute>
            <xsl:value-of select="$md5"/>
          </checksum>
        </file>
      </xsl:if>
    </xsl:copy>
  </xsl:template>

</xsl:stylesheet>
'''


  # 2017-05-15 TD : xslt specific to file addition to already transformed METS[DSpaceSIP|MODS].xml
  #                 Note again that, here too, there MUST NOT be any "<?xml ...>" header!
  #
  # 2017-07-11 TD : changed name of string variable to 'addfiles2mets'
  #
  # 2019-08-08 TD : fix the overriding 'identity rule' of the copying process
  #                 Only *one* file was added in the version before. Bad, bad, bad...
  #
  addfiles2mets = '''
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform" xmlns:mets="http://www.loc.gov/METS/">

  <xsl:output method="xml" omit-xml-declaration="no" standalone="no" indent="yes" encoding="utf-8"/>

  <xsl:param name="file"/>
  <xsl:param name="md5"/>
  <xsl:param name="mime"><xsl:text>application/octet-stream</xsl:text></xsl:param>
  <xsl:param name="cnt"><xsl:text>1</xsl:text></xsl:param>

  <xsl:template match="@*|node()">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()"/>
    </xsl:copy>
  </xsl:template>

  <xsl:template match="mets:mets">
    <xsl:copy>
      <xsl:apply-templates select="@* | *"/>
      <xsl:if test="not(./mets:fileSec/mets:fileGrp) and string-length($file)!=0 and string-length($md5)!=0">
        <mets:fileSec xmlns="http://www.loc.gov/METS/">
          <mets:fileGrp>
             <xsl:attribute name="ID"><xsl:text>sword-mets-fgrp-1</xsl:text></xsl:attribute>
             <xsl:attribute name="USE"><xsl:text>CONTENT</xsl:text></xsl:attribute>
             <mets:file>
               <xsl:attribute name="GROUPID">
                 <xsl:text>sword-mets-fgid-</xsl:text>
                 <xsl:value-of select="$cnt"/>
               </xsl:attribute>
               <xsl:attribute name="ID">
                 <xsl:text>sword-mets-file-</xsl:text>
                 <xsl:value-of select="format-number($cnt,'000')"/>
               </xsl:attribute>
               <xsl:attribute name="CHECKSUM">
                 <xsl:value-of select="$md5"/>
               </xsl:attribute>
               <xsl:attribute name="CHECKSUMTYPE">
                 <xsl:text>MD5</xsl:text>
               </xsl:attribute>
               <xsl:attribute name="MIMETYPE">
                 <xsl:value-of select="$mime"/>
               </xsl:attribute>
               <mets:FLocat xmlns:xlink="http://www.w3.org/1999/xlink">
                 <xsl:attribute name="LOCTYPE">
                   <xsl:text>URL</xsl:text>
                 </xsl:attribute>
                 <xsl:attribute name="xlink:href">
                   <xsl:value-of select="$file"/>
                 </xsl:attribute>
               </mets:FLocat>
             </mets:file>
          </mets:fileGrp>
        </mets:fileSec>
        <!--
        <structMap xmlns="http://www.loc.gov/METS/">
          <xsl:attribute name="ID"><xsl:text>sword-mets-struct-1</xsl:text></xsl:attribute>
          <xsl:attribute name="LABEL"><xsl:text>structure</xsl:text></xsl:attribute>
          <xsl:attribute name="TYPE"><xsl:text>LOGICAL</xsl:text></xsl:attribute>
          <div>
             <xsl:attribute name="ID"><xsl:text>sword-mets-div-1</xsl:text></xsl:attribute>
             <xsl:attribute name="DMDID"><xsl:value-of select="//mets:dmdSec/@ID"/></xsl:attribute>
             <xsl:attribute name="TYPE"><xsl:text>SWORD Object</xsl:text></xsl:attribute>
             <div>
                <xsl:attribute name="ID">
                  <xsl:text>sword-mets-div-</xsl:text>
                  <xsl:value-of select="$cnt + 1"/>
                </xsl:attribute>
                <xsl:attribute name="TYPE">
                  <xsl:text>File</xsl:text>
                </xsl:attribute>
                <fptr>
                   <xsl:attribute name="FILEID">
                     <xsl:text>sword-mets-file-</xsl:text>
                     <xsl:value-of select="format-number($cnt,'000')"/>
                   </xsl:attribute>
                </fptr>
             </div>
          </div>
        </structMap>
        -->
      </xsl:if>
    </xsl:copy>
  </xsl:template>
  
  <xsl:template match="mets:fileSec/mets:fileGrp">
    <xsl:copy>
      <xsl:apply-templates select="@* | *"/>
      <xsl:if test="string-length($file)!=0 and string-length($md5)!=0">
        <mets:file>
          <xsl:attribute name="GROUPID">
            <xsl:text>sword-mets-fgid-</xsl:text>
            <xsl:value-of select="$cnt"/>
          </xsl:attribute>
          <xsl:attribute name="ID">
            <xsl:text>sword-mets-file-</xsl:text>
            <xsl:value-of select="format-number($cnt,'000')"/>
          </xsl:attribute>
          <xsl:attribute name="CHECKSUM">
            <xsl:value-of select="$md5"/>
          </xsl:attribute>
          <xsl:attribute name="CHECKSUMTYPE">
            <xsl:text>MD5</xsl:text>
          </xsl:attribute>
          <xsl:attribute name="MIMETYPE">
            <xsl:value-of select="$mime"/>
          </xsl:attribute>
          <mets:FLocat xmlns:xlink="http://www.w3.org/1999/xlink">
            <xsl:attribute name="LOCTYPE">
              <xsl:text>URL</xsl:text>
            </xsl:attribute>
            <xsl:attribute name="xlink:href">
              <xsl:value-of select="$file"/>
            </xsl:attribute>
          </mets:FLocat>
        </mets:file>
      </xsl:if>
    </xsl:copy>
  </xsl:template>

  <!--
  <xsl:template match="/mets:mets/mets:structMap/div">
    <xsl:copy>
      <xsl:copy-of select="node()|@*"/>
      <xsl:if test="string-length($file)!=0 and string-length($md5)!=0">
        <div>
           <xsl:attribute name="ID">
             <xsl:text>sword-mets-div-</xsl:text>
             <xsl:value-of select="$cnt + 1"/>
           </xsl:attribute>
           <xsl:attribute name="TYPE">
             <xsl:text>File</xsl:text>
           </xsl:attribute>
           <fptr>
              <xsl:attribute name="FILEID">
                <xsl:text>sword-mets-file-</xsl:text>
                <xsl:value-of select="format-number($cnt,'000')"/>
              </xsl:attribute>
           </fptr>
        </div>
      </xsl:if>
    </xsl:copy>
  </xsl:template>
  -->

</xsl:stylesheet>
'''


  # 2018-03-20 TD : xslt specific to (final?) structMap addition to already transformed 
  #                 METS[DSpaceSIP|MODS].xml
  #                 In fact, this part is taken from addfiles2mets stylesheet above, 
  #                 since in the old version the case of /no/ file addition was not 
  #                 covered: The structMap part is compulsory, but would have been missed...
  #                 Note again that, here too, there MUST NOT be any "<?xml ...>" header!
  #
  # 2019-08-08 TD : fix the overriding 'identity rule' of the copying process
  #                 Only *one* file was added in the version before. Bad, bad, bad...
  #
  addstruct2mets = '''
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform" xmlns:mets="http://www.loc.gov/METS/">

  <xsl:output method="xml" omit-xml-declaration="no" standalone="no" indent="yes" encoding="utf-8"/>

  <xsl:template match="@*|node()">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()"/>
    </xsl:copy>
  </xsl:template>

  <xsl:template match="mets:mets">
    <xsl:copy>
      <xsl:apply-templates select="@* | *"/>
      <xsl:if test="not(./mets:structMap/div)">
        <mets:structMap xmlns="http://www.loc.gov/METS/">
          <xsl:attribute name="ID"><xsl:text>sword-mets-struct-1</xsl:text></xsl:attribute>
          <xsl:attribute name="LABEL"><xsl:text>structure</xsl:text></xsl:attribute>
          <xsl:attribute name="TYPE"><xsl:text>LOGICAL</xsl:text></xsl:attribute>
          <div>
             <xsl:attribute name="ID"><xsl:text>sword-mets-div-0</xsl:text></xsl:attribute>
             <xsl:attribute name="DMDID"><xsl:value-of select="//mets:dmdSec/@ID"/></xsl:attribute>
             <xsl:attribute name="TYPE"><xsl:text>SWORD Object</xsl:text></xsl:attribute>
             <xsl:for-each select="//mets:fileSec/mets:fileGrp/mets:file">
                <div>
                   <xsl:attribute name="ID">
                     <xsl:text>sword-mets-div-</xsl:text>
                     <xsl:value-of select="position()"/>
                     <!--
                     <xsl:value-of select="$cnt + 1"/>
                     -->
                   </xsl:attribute>
                   <xsl:attribute name="TYPE">
                     <xsl:text>File</xsl:text>
                   </xsl:attribute>
                   <fptr>
                      <xsl:attribute name="FILEID">
                        <xsl:value-of select="./@ID"/>
                        <!--
                        <xsl:text>sword-mets-file-</xsl:text>
                        <xsl:value-of select="format-number($cnt,'000')"/>
                        -->
                      </xsl:attribute>
                   </fptr>
                </div>
             </xsl:for-each>
          </div>
        </mets:structMap>
      </xsl:if>
    </xsl:copy>
  </xsl:template>

  <!--
  <xsl:template match="/mets:mets/structMap/div">
    <xsl:copy>
      <xsl:copy-of select="node()|@*"/>
      <xsl:if test="string-length($file)!=0 and string-length($md5)!=0">
        <div>
           <xsl:attribute name="ID">
             <xsl:text>sword-mets-div-</xsl:text>
             <xsl:value-of select="$cnt + 1"/>
           </xsl:attribute>
           <xsl:attribute name="TYPE">
             <xsl:text>File</xsl:text>
           </xsl:attribute>
           <fptr>
              <xsl:attribute name="FILEID">
                <xsl:text>sword-mets-file-</xsl:text>
                <xsl:value-of select="format-number($cnt,'000')"/>
              </xsl:attribute>
           </fptr>
        </div>
      </xsl:if>
    </xsl:copy>
  </xsl:template>
  -->

</xsl:stylesheet>
'''

  def __init__(self):
    pass

