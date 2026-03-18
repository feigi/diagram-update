<goal>a tool which is able to automatically create or update various forms of software component diagrams automatically without user input and high certainty for correctnes</goal>

<requirements>
<li>Must be able to create human readable diagrams (i.e. not too overloaded, little to no crossing edges)</li>
<li>Must keep existing diagrams stable (i.e. as little changes as possible while keeping human readability high)</li>
<li>Must be efficient in terms of runtime and token usage</li>
<li>Must allow for configuration to guide the creation process if required (e.g. user specifies set of components to inform diagram granularity or exlusion of certain components...)</li>
</requirements>

<validation>
<AFTER_RALPH_LOOP>
	<li>Multiple dummy projects (e.g. clone trustworthy public repos)</li>
	<li>Create initial diagram and let user rate readability from 1 to 10<. The user will acknowledge when the average score among all dummy projects is good enough</li>
	<li>Make 5 different changes to the code, ranging from small additions to big architectural refactoring. apply each change to the same state of the code. for each change run the tool again. Present the old vs. new diagram to the user and ask for 'Good' or 'Bad'</li>
</AFTER_RALPH_LOOP>
</validation>


